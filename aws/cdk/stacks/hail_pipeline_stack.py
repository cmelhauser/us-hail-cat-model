"""Hail pipeline ECS Fargate + EFS stack driven by pipeline.yaml."""

from __future__ import annotations

from typing import Any

import aws_cdk as cdk
from aws_cdk import CfnOutput, RemovalPolicy, Stack
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_ecr as ecr
from aws_cdk import aws_ecs as ecs
from aws_cdk import aws_efs as efs
from aws_cdk import aws_iam as iam
from aws_cdk import aws_logs as logs
from constructs import Construct

from hail_aws.config import PipelineConfig, TaskSpec


class HailPipelineStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        config: PipelineConfig,
        **kwargs: Any,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        self.config = config

        for key, value in config.tags.items():
            cdk.Tags.of(self).add(key, value)

        vpc = self._vpc()
        cluster = ecs.Cluster(
            self,
            "Cluster",
            cluster_name=config.cluster_name,
            vpc=vpc,
            container_insights=True,
        )

        repo = ecr.Repository(
            self,
            "Repository",
            repository_name=config.image_repository,
            image_scan_on_push=True,
            removal_policy=RemovalPolicy.RETAIN,
        )

        log_group = logs.LogGroup(
            self,
            "LogGroup",
            log_group_name=config.log_group,
            retention=logs.RetentionDays.ONE_MONTH,
            removal_policy=RemovalPolicy.DESTROY,
        )

        file_system = efs.FileSystem(
            self,
            "DataEfs",
            vpc=vpc,
            encrypted=config.efs_encrypted,
            performance_mode=efs.PerformanceMode.GENERAL_PURPOSE,
            throughput_mode=efs.ThroughputMode.BURSTING,
            removal_policy=RemovalPolicy.RETAIN,
        )

        task_sg = ec2.SecurityGroup(
            self,
            "TaskSecurityGroup",
            vpc=vpc,
            description="Hail pipeline Fargate tasks",
            allow_all_outbound=True,
        )
        file_system.connections.allow_default_port_from(task_sg, "NFS from tasks")

        execution_role = iam.Role(
            self,
            "ExecutionRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AmazonECSTaskExecutionRolePolicy"
                )
            ],
        )
        task_role = iam.Role(
            self,
            "TaskRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
        )
        file_system.grant_root_access(task_role)
        for arn in (config.cdsapi_secret_arn, config.ncar_rda_secret_arn):
            if arn:
                task_role.add_to_policy(
                    iam.PolicyStatement(
                        actions=["secretsmanager:GetSecretValue"],
                        resources=[arn],
                    )
                )

        # One access point per mount (EFS forbids root_directory with access points).
        mount_specs = (
            ("data", config.data_mount, "/data"),
            ("logs", config.logs_mount, "/logs"),
            ("figures", config.figures_mount, "/figures"),
        )
        volumes = []
        for label, _mount, ap_path in mount_specs:
            ap = file_system.add_access_point(
                f"Ap{label.capitalize()}",
                path=ap_path,
                create_acl=efs.Acl(
                    owner_uid="1001", owner_gid="1001", permissions="755"
                ),
                posix_user=efs.PosixUser(uid="1001", gid="1001"),
            )
            volumes.append(
                ecs.Volume(
                    name=f"hail-{label}",
                    efs_volume_configuration=ecs.EfsVolumeConfiguration(
                        file_system_id=file_system.file_system_id,
                        transit_encryption="ENABLED",
                        authorization_config=ecs.AuthorizationConfig(
                            access_point_id=ap.access_point_id,
                            iam="ENABLED",
                        ),
                    ),
                )
            )

        task_defs: dict[str, ecs.FargateTaskDefinition] = {}
        for name, spec in config.tasks.items():
            task_defs[name] = self._task_definition(
                name=name,
                spec=spec,
                repo=repo,
                log_group=log_group,
                execution_role=execution_role,
                task_role=task_role,
                volumes=volumes,
                mount_specs=mount_specs,
            )

        public_subnets = vpc.select_subnets(subnet_type=ec2.SubnetType.PUBLIC).subnets
        subnet_ids = ",".join(s.subnet_id for s in public_subnets)

        CfnOutput(self, "ClusterName", value=cluster.cluster_name)
        CfnOutput(self, "ClusterArn", value=cluster.cluster_arn)
        CfnOutput(self, "RepositoryUri", value=repo.repository_uri)
        CfnOutput(self, "SubnetIds", value=subnet_ids)
        CfnOutput(self, "TaskSecurityGroupId", value=task_sg.security_group_id)
        CfnOutput(self, "EfsId", value=file_system.file_system_id)
        for name, td in task_defs.items():
            family = config.tasks[name].family
            CfnOutput(self, f"TaskDef{family}", value=td.task_definition_arn)

    def _vpc(self) -> ec2.IVpc:
        cfg = self.config
        if cfg.vpc_id:
            return ec2.Vpc.from_lookup(self, "ImportedVpc", vpc_id=cfg.vpc_id)
        return ec2.Vpc(
            self,
            "Vpc",
            max_azs=cfg.max_azs,
            nat_gateways=0,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24,
                )
            ],
        )

    def _task_definition(
        self,
        *,
        name: str,
        spec: TaskSpec,
        repo: ecr.Repository,
        log_group: logs.LogGroup,
        execution_role: iam.Role,
        task_role: iam.Role,
        volumes: list,
        mount_specs: tuple[tuple[str, str, str], ...],
    ) -> ecs.FargateTaskDefinition:
        cfg = self.config
        td = ecs.FargateTaskDefinition(
            self,
            f"TaskDef{name}",
            family=spec.family,
            cpu=spec.cpu,
            memory_limit_mib=spec.memory,
            execution_role=execution_role,
            task_role=task_role,
            ephemeral_storage_gib=spec.ephemeral_storage_gib,
            runtime_platform=ecs.RuntimePlatform(
                operating_system_family=ecs.OperatingSystemFamily.LINUX,
                cpu_architecture=ecs.CpuArchitecture.X86_64,
            ),
        )
        for vol in volumes:
            td.add_volume(
                name=vol.name,
                efs_volume_configuration=vol.efs_volume_configuration,
            )

        image = ecs.ContainerImage.from_ecr_repository(repo, tag=cfg.image_tag)
        container = td.add_container(
            "hail",
            image=image,
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix=spec.family,
                log_group=log_group,
            ),
            command=list(spec.command),
            environment={
                "OPENBLAS_NUM_THREADS": "1",
                "PYTHONUNBUFFERED": "1",
                "HAIL_PIPELINE_TASK": name,
            },
            essential=True,
        )
        for label, container_path, _root in mount_specs:
            container.add_mount_points(
                ecs.MountPoint(
                    container_path=container_path,
                    source_volume=f"hail-{label}",
                    read_only=False,
                )
            )
        return td

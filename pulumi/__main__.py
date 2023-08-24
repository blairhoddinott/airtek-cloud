import base64
import json

import pulumi
import pulumi_aws as aws
import pulumi_docker as docker


def getRegistryInfo(rid):
    creds = aws.ecr.get_credentials(registry_id=rid)
    decoded = base64.b64decode(creds.authorization_token).decode()
    parts = decoded.split(":")
    if len(parts) != 2:
        raise Exception("Invalid Credentials")
    return docker.ImageRegistry(creds.proxy_endpoint, parts[0], parts[1])


# VPC Defaults
default_vpc = aws.ec2.get_vpc(default=True)
default_subnets = aws.ec2.get_subnets()

# ECR
fe_repo = aws.ecr.Repository(
    "frontend",
    tags={
        'Environment': 'Dev',
        'ResourceType': 'ECR',
        'Component': 'Frontend'
    },
)
fe_registry_info = fe_repo.registry_id.apply(getRegistryInfo)

be_repo = aws.ecr.Repository(
    "backend",
    tags={
        'Environment': 'Dev',
        'ResourceType': 'ECR',
        'Component': 'Backend'
    },
)
be_registry_info = be_repo.registry_id.apply(getRegistryInfo)

frontend_image_name = fe_repo.repository_url
frontend = docker.Image(
    "frontend",
    build="frontend",

    image_name=frontend_image_name,
    registry=fe_registry_info,
)

backend_image_name = be_repo.repository_url
backend = docker.Image(
    "backend",
    build="backend",
    image_name=backend_image_name,
    registry=be_registry_info,
)

# IAM
task_execution_role = aws.iam.Role(
    'TaskExecutionRole',
    assume_role_policy=pulumi.Output.from_input(
        aws.iam.get_policy_document(
            statements=[
                aws.iam.GetPolicyDocumentStatementArgs(
                    actions=[
                        "sts:AssumeRole",
                    ],
                    principals=[
                        aws.iam.GetPolicyDocumentStatementPrincipalArgs(
                            type='Service',
                            identifiers=[
                                'ecs-tasks.amazonaws.com',
                            ],
                        )
                    ],
                )
            ]
        ).json
    )
)

task_execution_attachment = aws.iam.RolePolicyAttachment(
    'TaskExecutionRolePolicyAttachment',
    role=task_execution_role.id,
    policy_arn='arn:aws:iam::aws:policy/service-role/'
               'AmazonECSTaskExecutionRolePolicy',
)

# ALB
public_sg = aws.ec2.SecurityGroup(
    'http_ingress',
    vpc_id=default_vpc.id,
    ingress=[
        aws.ec2.SecurityGroupIngressArgs(
            protocol='TCP',
            from_port=80,
            to_port=80,
            cidr_blocks=['0.0.0.0/0'],
        ),
    ],
    egress=[
        aws.ec2.SecurityGroupEgressArgs(
            protocol='-1',
            from_port=0,
            to_port=0,
            cidr_blocks=['0.0.0.0/0']
        )
    ],
    tags={
        'Environment': 'Dev',
        'ResourceType': 'Security Group',
        'Component': 'Frontend',
        'Access-Type': 'Public'
    },
)

ecs_sg = aws.ec2.SecurityGroup(
    'ecs_security_group',
    vpc_id=default_vpc.id,
    ingress=[
        aws.ec2.SecurityGroupIngressArgs(
            protocol='TCP',
            from_port=5000,
            to_port=5000,
            cidr_blocks=['0.0.0.0/0']
        ),
    ],
    egress=[
        aws.ec2.SecurityGroupEgressArgs(
            protocol='-1',
            from_port=0,
            to_port=0,
            cidr_blocks=['0.0.0.0/0']
        )
    ],
    tags={
        'Environment': 'Dev',
        'ResourceType': 'Security Group',
        'Component': 'Frontend, Backend',
        'Access-Type': 'Internal'
    },
)

internal_lb_sg = aws.ec2.SecurityGroup(
    'internal_lb_security_group',
    vpc_id=default_vpc.id,
    ingress=[
        aws.ec2.SecurityGroupIngressArgs(
            protocol='TCP',
            from_port=5000,
            to_port=5000,
            cidr_blocks=['172.31.0.0/16']
        ),
    ],
    egress=[
        aws.ec2.SecurityGroupEgressArgs(
            protocol='-1',
            from_port=0,
            to_port=0,
            cidr_blocks=['0.0.0.0/0']
        )
    ],
    tags={
        'Environment': 'Dev',
        'ResourceType': 'Security Group',
        'Component': 'Backend',
        'Access-Type': 'Internal'
    },
)

lb = aws.lb.LoadBalancer(
    'at-lb-001',
    internal=False,
    load_balancer_type='application',
    security_groups=[public_sg.id],
    subnets=default_subnets.ids,
    tags={
        'Environment': 'Dev',
        'ResourceType': 'External Load Balancer',
        'Component': 'Frontend',
        'Access-Type': 'External'
    },
)
pulumi.export("external_url", pulumi.Output.concat("http://", lb.dns_name))

ilb = aws.lb.LoadBalancer(
    'at-ilb-001',
    internal=True,
    load_balancer_type='application',
    security_groups=[internal_lb_sg.id],
    subnets=default_subnets.ids,
    tags={
        'Environment': 'Dev',
        'ResourceType': 'Internal Load Balancer',
        'Component': 'Backend',
        'Access-Type': 'Internal'
    },
)
pulumi.export("internal_url", pulumi.Output.concat("http://", ilb.dns_name))

fe_target_group = aws.lb.TargetGroup(
    'frontend-tg',
    port=5000,
    protocol='HTTP',
    target_type='ip',
    vpc_id=default_vpc.id)

be_target_group = aws.lb.TargetGroup(
    'backend-tg',
    port=5000,
    protocol='HTTP',
    target_type='ip',
    vpc_id=default_vpc.id)

fe_listener = aws.lb.Listener(
    'fe-listener',
    load_balancer_arn=lb.arn,
    port=80,
    default_actions=[
        aws.lb.ListenerDefaultActionArgs(
            type='forward',
            target_group_arn=fe_target_group.arn,
        ),
    ])

be_listener = aws.lb.Listener(
    'be-listener',
    load_balancer_arn=ilb.arn,
    port=5000,
    default_actions=[
        aws.lb.ListenerDefaultActionArgs(
            type='forward',
            target_group_arn=be_target_group.arn,
        ),
    ])

# ECS
fe_cluster = aws.ecs.Cluster(
    'at-ecs-cluster-001',
    tags={
        'Environment': 'Dev',
        'ResourceType': 'ECS Cluster',
        'Component': 'Frontend'
    },
)
be_cluster = aws.ecs.Cluster(
    'at-ecs-cluster-002',
    tags={
        'Environment': 'Dev',
        'ResourceType': 'ECS Cluster',
        'Component': 'Backend'
    },
)
url = pulumi.Output.all(ilb.dns_name).apply(
    lambda args:
    f"http://{args[0]}:5000/WeatherForecast"
)

fe_task_definition = aws.ecs.TaskDefinition(
    'frontend',
    family='airtek',
    cpu='256',
    memory='512',
    network_mode='awsvpc',
    requires_compatibilities=['FARGATE'],
    execution_role_arn=task_execution_role.arn,
    container_definitions=pulumi.Output.from_input([{
        'name': 'frontend',
        'image': frontend.image_name,
        'portMappings': [{
            'containerPort': 5000,
            'hostPort': 5000,
            'protocol': 'http',
        }],
        'environment': [{
            "name": "ApiAddress",
            "value": url
        }]
    }]).apply(lambda cs: json.dumps(cs)),
)

fe_service = aws.ecs.Service(
    'frontend',
    cluster=fe_cluster.arn,
    desired_count=1,
    launch_type='FARGATE',
    task_definition=fe_task_definition.arn,
    network_configuration=aws.ecs.ServiceNetworkConfigurationArgs(
        assign_public_ip=True,
        subnets=default_subnets.ids,
        security_groups=[ecs_sg.id],
    ),
    load_balancers=[
        aws.ecs.ServiceLoadBalancerArgs(
            target_group_arn=fe_target_group.arn,
            container_name='frontend',
            container_port=5000,
        ),
    ],
    tags={
        'Environment': 'Dev',
        'ResourceType': 'Fargate Service',
        'Component': 'Frontend'
    },
)

be_task_definition = aws.ecs.TaskDefinition(
    'backend',
    family='airtek',
    cpu='256',
    memory='512',
    network_mode='awsvpc',
    requires_compatibilities=['FARGATE'],
    execution_role_arn=task_execution_role.arn,
    container_definitions=pulumi.Output.from_input([{
        'name': 'backend',
        'image': backend.image_name,
        'portMappings': [{
            'containerPort': 5000,
            'hostPort': 5000,
            'protocol': 'http',
        }],
    }]).apply(lambda cs: json.dumps(cs)),
)

be_service = aws.ecs.Service(
    'backend',
    cluster=be_cluster.arn,
    desired_count=1,
    launch_type='FARGATE',
    task_definition=be_task_definition.arn,
    network_configuration=aws.ecs.ServiceNetworkConfigurationArgs(
        assign_public_ip=True,
        subnets=default_subnets.ids,
        security_groups=[ecs_sg.id],
    ),
    load_balancers=[
        aws.ecs.ServiceLoadBalancerArgs(
            target_group_arn=be_target_group.arn,
            container_name='backend',
            container_port=5000,
        ),
    ],
    tags={
        'Environment': 'Dev',
        'ResourceType': 'Fargate Service',
        'Component': 'Backend'
    },
)

pulumi.export("fe_image_url", frontend_image_name)
pulumi.export("be_image_url", backend_image_name)
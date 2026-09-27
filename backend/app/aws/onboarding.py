"""What the user deploys in their own account to connect it.

A CloudFormation template rather than an IAM user with access keys: the user clicks through a stack,
Ward gets a role it can assume, and nothing secret ever travels between the two. The permissions are
exactly SRS §7 — Describe/List/Get plus Cost Explorer, and no Delete, Terminate or iam:*.
"""
from urllib.parse import quote

from app.config import settings

STACK_NAME = 'ward-readonly'

# Kept as text, not a dict, because the user reads it before deploying it. The parameters carry
# defaults when rendered for one account, so deploying takes no typing — only the ExternalId is
# per-account, and Ward fills it in rather than asking the user to copy it across.
_TEMPLATE = '''AWSTemplateFormatVersion: "2010-09-09"
Description: Read-only role for Ward (natural-language cloud cost guardrails)

Parameters:
  WardPrincipal:
    Type: String
    Description: The Ward IAM principal allowed to assume this role{ward_default}
  ExternalId:
    Type: String
    Description: The shared secret Ward issued for this account
    NoEcho: true{external_default}

Resources:
  WardReadOnlyRole:
    Type: AWS::IAM::Role
    Properties:
      RoleName: WardReadOnly
      Description: Lets Ward read inventory and cost data. No write permissions.
      AssumeRolePolicyDocument:
        Version: "2012-10-17"
        Statement:
          - Effect: Allow
            Principal:
              AWS: !Ref WardPrincipal
            Action: sts:AssumeRole
            Condition:
              StringEquals:
                sts:ExternalId: !Ref ExternalId
      Policies:
        - PolicyName: WardRead
          PolicyDocument:
            Version: "2012-10-17"
            Statement:
              - Effect: Allow
                Action:
                  - ec2:Describe*
                  - rds:Describe*
                  - s3:List*
                  - s3:GetBucket*
                  - eks:Describe*
                  - eks:List*
                  - ce:GetCostAndUsage
                  - ce:GetCostForecast
                  - cloudwatch:GetMetricStatistics
                Resource: "*"

Outputs:
  RoleArn:
    Description: Paste this back into Ward
    Value: !GetAtt WardReadOnlyRole.Arn
'''

# The hostable form: parameters with no defaults, for the one-click console link.
TEMPLATE = _TEMPLATE.format(ward_default='', external_default='')


def rendered(external_id: str, principal: str | None) -> str:
    """The same template with this account's values already in it, so a manual deploy needs no typing.

    With no principal the WardPrincipal default is left out: a placeholder would deploy into a trust
    policy IAM rejects, which is a worse failure than an empty field the console asks you to fill.
    """
    return _TEMPLATE.format(
        ward_default=f'\n    Default: {principal}' if principal else '',
        external_default=f'\n    Default: {external_id}',
    )


def instructions(external_id: str, principal: str | None) -> dict:
    """Everything the UI needs to walk one account through connecting."""
    return {
        'stack_name': STACK_NAME,
        'ward_principal': principal,
        'ready': principal is not None,
        'external_id': external_id,
        'template': rendered(external_id, principal),
        'quick_create_url': _quick_create_url(external_id, principal),
        'cli': [
            f'aws cloudformation deploy --template-file {STACK_NAME}.yaml --stack-name {STACK_NAME} '
            f'--capabilities CAPABILITY_NAMED_IAM',
            f'aws cloudformation describe-stacks --stack-name {STACK_NAME} '
            f'--query "Stacks[0].Outputs[?OutputKey==\'RoleArn\'].OutputValue" --output text',
        ],
        'steps': [
            'Deploy the template below in the AWS account you want Ward to watch.',
            'It creates one role, WardReadOnly, with read-only permissions and no ability to change anything.',
            'When the stack finishes, copy the RoleArn output.',
            'Send it back to Ward with POST /accounts/{id}/connect to finish.',
        ],
        'permissions': [
            'ec2:Describe*', 'rds:Describe*', 's3:List*', 's3:GetBucket*', 'eks:Describe*', 'eks:List*',
            'ce:GetCostAndUsage', 'ce:GetCostForecast', 'cloudwatch:GetMetricStatistics',
        ],
    }


def _quick_create_url(external_id: str, principal: str | None) -> str | None:
    """A one-click console link — only possible once the template is hosted at a public URL."""
    if not settings.cfn_template_url or not principal:
        return None
    return (
        'https://console.aws.amazon.com/cloudformation/home#/stacks/create/review'
        f'?templateURL={quote(settings.cfn_template_url, safe="")}'
        f'&stackName={STACK_NAME}'
        f'&param_WardPrincipal={quote(principal, safe="")}'
        f'&param_ExternalId={quote(external_id, safe="")}'
    )

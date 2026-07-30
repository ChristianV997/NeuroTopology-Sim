"""Placeholder AWS configuration for the autonomous orchestrator.

Fill these in after running scripts/setup_aws.ps1. RESULTS_BUCKET is printed
at the end of that script; AMI_ID/KEY_NAME must be created once in the AWS
console (or CLI) before orchestrator.job_router can submit Spot jobs.
"""

REGION = "us-east-1"
RESULTS_BUCKET = "neurotopology-results-XXXXX"  # set after scripts/setup_aws.ps1
AMI_ID = "ami-0c02fb55956c7d316"  # Amazon Linux 2, us-east-1 -- verify/update per region
KEY_NAME = "neurotopology-key"  # EC2 key pair, create once in the AWS console
INSTANCE_TYPE_GPU = "g4dn.xlarge"  # PITNN training (~$0.16/hr spot)
INSTANCE_TYPE_CPU = "c6i.4xlarge"  # fMRI TDA pipeline (~$0.27/hr spot)

# file: scripts/check_wandb_models.py
import os
import urllib3
import wandb
from wandb.errors import CommError
import dataikuapi
from dataikuapi import DSSClient

# --- CI-friendly: read all creds from env (set as GitHub Secrets) ---

# Disable warnings for unverified HTTPS requests
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Access environment variables
DATAIKU_API_TOKEN_DEV = os.getenv('DATAIKU_API_TOKEN_DEV')
DATAIKU_API_TOKEN_STAGING = os.getenv('DATAIKU_API_TOKEN_PROD')
DATAIKU_API_TOKEN_PROD = os.getenv('DATAIKU_API_TOKEN_PROD')
DATAIKU_INSTANCE_DEV_URL = os.getenv('DATAIKU_INSTANCE_DEV_URL')
DATAIKU_INSTANCE_STAGING_URL = os.getenv('DATAIKU_INSTANCE_PROD_URL')
DATAIKU_INSTANCE_PROD_URL = os.getenv('DATAIKU_INSTANCE_PROD_URL')
DATAIKU_PROJECT_KEY = os.getenv('DATAIKU_PROJECT_KEY')
DATAIKU_INFRA_ID_STAGING = os.getenv('DATAIKU_INFRA_ID_PROD')
DATAIKU_INFRA_ID_PROD = os.getenv('DATAIKU_INFRA_ID_PROD')
RUN_TESTS_ONLY = os.getenv('RUN_TESTS_ONLY', 'false').lower() == 'true'
PYTHON_SCRIPT = os.getenv('PYTHON_SCRIPT', 'tests.py')
CLIENT_CERTIFICATE = os.getenv('CLIENT_CERTIFICATE', None)

#WANDB_API_KEY        = os.getenv("WANDB_API_KEY")


# Connect to DSS
client = dataikuapi.DSSClient(DATAIKU_INSTANCE_DEV_URL, DATAIKU_API_TOKEN_DEV, no_check_certificate=True, client_certificate=CLIENT_CERTIFICATE)


project = client.get_project(DATAIKU_PROJECT_KEY)
print(f"Connected to Dataiku project: {DATAIKU_PROJECT_KEY}")

# --- Retrieve authentication info with secrets ---
auth_info = client.get_auth_info(with_secrets=True)
secret_value = None
for secret in auth_info.get("secrets", []):
    if secret.get("key") == "wandbcred":
        secret_value = secret.get("value")
        break
if not secret_value:
    raise Exception("Secret 'wandbcred' not found")


# W&B login / API
wandb.login(key=WANDB_API_KEY)
api = wandb.Api()

# List DSS saved models
saved_model_ids = [sm["id"] for sm in project.list_saved_models()]
if not saved_model_ids:
    print("W&B DEBUG: No saved models found in Dataiku.")
    exit(0)

# Collect ALL W&B model artifacts once
artifacts = []
try:
    for collection in api.registries().collections():
        for artifact in collection.artifacts():
            if artifact.type and artifact.type.lower() == "model":
                artifacts.append({
                    "collection": collection.name,
                    "artifact": artifact.source_name,   # e.g. "dataiku-<sm>-<ver>:v0"
                    "path": artifact.qualified_name     # e.g. "entity/project/artifact:version"
                })
except CommError as e:
    raise RuntimeError(f"Failed to list W&B artifacts: {e}")

artifact_names = [{"name": a["artifact"], "path": a["path"]} for a in artifacts]
any_published = False

for sm in saved_model_ids:
    print("✅----- Checking Model(s) in Dataiku -----")
    print(f"Dataiku Current Saved Model : {sm}")

    model = project.get_saved_model(sm)
    active_id = model.get_active_version()["id"]
    _ = model.get_version_details(active_id)  # placeholder for future use

    model_identifier = f"dataiku-{sm}-{active_id}"
    print(f"Dataiku Model Identifier  : {model_identifier}")
    print("----- Checking if Model exists in W&B -----")

    candidate_artifacts = [a for a in artifact_names if model_identifier in a["name"]]

    if not candidate_artifacts:
        print("⚠️  No published W&B artifacts found for this model.\n")
        continue

    any_published = True
    for art in candidate_artifacts:
        wb_name_full = art["name"]               # e.g. "dataiku-4wUI1vp8-1702915444643:v0"
        if ":" in wb_name_full:
            wb_name_base, wb_version = wb_name_full.split(":", 1)
        else:
            wb_name_base, wb_version = wb_name_full, None

        print("✅ Published Model Found in W&B")
        print(f"   Full Artifact Name : {wb_name_full}")
        print(f"   Base Name          : {wb_name_base}")
        print(f"   W&B Version        : {wb_version}")
        print(f"   Registry Path      : {art['path']}")
        print("------------------------------")

if not any_published:
    print("🛑 W&B DEBUG: No models are published to W&B for any saved models.")
    # Optional: make the CI fail if nothing is published
    if os.getenv("FAIL_ON_NO_PUBLISH", "false").lower() == "true":
        exit(1)

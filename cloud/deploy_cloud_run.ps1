$ErrorActionPreference = "Stop"

$PROJECT_ID = "corekorean"
$REGION = "us-central1"
$SERVICE = "corekorean"
$REPO = "corekorean"
$IMAGE = "${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/${SERVICE}:latest"

# Create the Artifact Registry repo if it is not there yet.
try {
    gcloud artifacts repositories create $REPO `
        --repository-format=docker `
        --location=$REGION `
        --project=$PROJECT_ID `
        --quiet
}
catch {
    Write-Host "Artifact Registry repository may already exist; continuing..."
}

# Let Docker push to Artifact Registry.
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet

# Build and upload the container.
docker build -t $IMAGE .
docker push $IMAGE

# Deploy the container to Cloud Run.
gcloud run deploy $SERVICE `
    --image=$IMAGE `
    --platform=managed `
    --region=$REGION `
    --allow-unauthenticated `
    --port=8080 `
    --project=$PROJECT_ID

# Print the public service URL.
gcloud run services describe $SERVICE `
    --platform=managed `
    --region=$REGION `
    --format="value(status.url)" `
    --project=$PROJECT_ID

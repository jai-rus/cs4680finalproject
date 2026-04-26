param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectId,

    [string]$Region = "us-central1",
    [string]$Service = "corekorean",
    [string]$Repository = "corekorean"
)

$ErrorActionPreference = "Stop"

$image = "$Region-docker.pkg.dev/$ProjectId/$Repository/$Service`:latest"

gcloud config set project $ProjectId | Out-Null

$repoExists = gcloud artifacts repositories describe $Repository `
    --location $Region `
    --project $ProjectId `
    --format "value(name)" 2>$null

if (-not $repoExists) {
    gcloud artifacts repositories create $Repository `
        --repository-format docker `
        --location $Region `
        --description "CoreKorean container images" `
        --project $ProjectId
}

gcloud builds submit `
    --tag $image `
    --project $ProjectId

gcloud run deploy $Service `
    --image $image `
    --region $Region `
    --platform managed `
    --allow-unauthenticated `
    --project $ProjectId

param(
    [Parameter(Mandatory = $true)]
    [string]$ResourceGroupName,

    [Parameter(Mandatory = $true)]
    [string]$Location,

    [Parameter(Mandatory = $true)]
    [string]$ResourcePrefix,

    [string]$EnvFilePath = ".env.azure",

    [string]$SubscriptionId,

    [switch]$BootstrapInfra
)

$ErrorActionPreference = "Stop"

function Get-NormalizedPrefix {
    param([string]$Prefix)

    return $Prefix.ToLower()
}

function Get-AcrName {
    param([string]$Prefix)

    $normalized = ($Prefix.ToLower() -replace "-", "")
    $name = "$normalized" + "acr"
    if ($name.Length -gt 50) {
        return $name.Substring(0, 50)
    }
    return $name
}

function Read-EnvFile {
    param([string]$Path)

    if (-not (Test-Path $Path)) {
        throw "Env file not found: $Path"
    }

    $values = @{}
    Get-Content $Path | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#")) {
            return
        }

        $parts = $line.Split("=", 2)
        if ($parts.Count -ne 2) {
            return
        }

        $values[$parts[0].Trim()] = $parts[1].Trim()
    }

    return $values
}

function Get-SecretName {
    param([string]$EnvName)

    return $EnvName.ToLower().Replace("_", "-")
}

if ($SubscriptionId) {
    az account set --subscription $SubscriptionId | Out-Null
}

$normalizedPrefix = Get-NormalizedPrefix -Prefix $ResourcePrefix
$acrName = Get-AcrName -Prefix $ResourcePrefix
$containerAppName = "$normalizedPrefix-backend"
$imageRepository = "gatekeeper-backend"
$timestampTag = Get-Date -Format "yyyyMMdd-HHmmss"
$imageName = "$imageRepository:$timestampTag"
$fullImageName = "$acrName.azurecr.io/$imageName"

if ($BootstrapInfra) {
    az group create --name $ResourceGroupName --location $Location | Out-Null
    az deployment group create `
        --resource-group $ResourceGroupName `
        --template-file infra/main.bicep `
        --parameters "@infra/main.parameters.json" `
        --parameters location=$Location resourcePrefix=$ResourcePrefix | Out-Null
}

$envValues = Read-EnvFile -Path $EnvFilePath

$secretKeys = @(
    "SECRET_KEY",
    "GITLAB_CLIENT_ID",
    "GITLAB_CLIENT_SECRET",
    "GITLAB_PERSONAL_ACCESS_TOKEN",
    "MDB_MCP_CONNECTION_STRING",
    "GATEKEEPER_ENCRYPTION_KEY",
    "ARIZE_API_KEY",
    "ARIZE_SPACE_ID",
    "PHOENIX_API_KEY"
)

$secretArgs = @()
$envArgs = @("PORT=8000")

foreach ($entry in $envValues.GetEnumerator()) {
    $key = $entry.Key
    $value = $entry.Value

    if ([string]::IsNullOrWhiteSpace($value)) {
        continue
    }

    if ($secretKeys -contains $key) {
        $secretName = Get-SecretName -EnvName $key
        $secretArgs += "$secretName=$value"
        $envArgs += "$key=secretref:$secretName"
    }
    else {
        $envArgs += "$key=$value"
    }
}

az acr build --registry $acrName --image $imageName . | Out-Null

if ($secretArgs.Count -gt 0) {
    az containerapp secret set `
        --name $containerAppName `
        --resource-group $ResourceGroupName `
        --secrets $secretArgs | Out-Null
}

az containerapp update `
    --name $containerAppName `
    --resource-group $ResourceGroupName `
    --image $fullImageName `
    --set-env-vars $envArgs | Out-Null

$fqdn = az containerapp show `
    --name $containerAppName `
    --resource-group $ResourceGroupName `
    --query properties.configuration.ingress.fqdn `
    --output tsv

Write-Host "Release complete"
Write-Host "Image: $fullImageName"
Write-Host "Backend URL: https://$fqdn"

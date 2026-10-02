param(
  [string]$WebBaseUrl,
  [string]$ApiBaseUrl,
  [string]$Email,
  [string]$Password,
  [string]$OrganizationId,
  [string]$StoreId,
  [string]$AwsRegion,
  [string]$CognitoClientId,
  [switch]$PublicOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($WebBaseUrl)) {
  $WebBaseUrl = if ($env:E2E_WEB_URL) { $env:E2E_WEB_URL } else { "https://diaglob.tech" }
}
if ([string]::IsNullOrWhiteSpace($ApiBaseUrl)) {
  $ApiBaseUrl = if ($env:E2E_API_URL) { $env:E2E_API_URL } else { "https://api.diaglob.tech" }
}
if ([string]::IsNullOrWhiteSpace($Email) -and $env:E2E_EMAIL) {
  $Email = $env:E2E_EMAIL
}
if ([string]::IsNullOrWhiteSpace($Password) -and $env:E2E_PASSWORD) {
  $Password = $env:E2E_PASSWORD
}
if ([string]::IsNullOrWhiteSpace($OrganizationId) -and $env:E2E_ORGANIZATION_ID) {
  $OrganizationId = $env:E2E_ORGANIZATION_ID
}
if ([string]::IsNullOrWhiteSpace($StoreId) -and $env:E2E_STORE_ID) {
  $StoreId = $env:E2E_STORE_ID
}
if ([string]::IsNullOrWhiteSpace($AwsRegion)) {
  $AwsRegion = if ($env:E2E_AWS_REGION) { $env:E2E_AWS_REGION } else { "us-east-2" }
}
if ([string]::IsNullOrWhiteSpace($CognitoClientId)) {
  $CognitoClientId = if ($env:E2E_COGNITO_CLIENT_ID) { $env:E2E_COGNITO_CLIENT_ID } else { "7gas2mvvovukjpk05jhbku4303" }
}

$WebBaseUrl = $WebBaseUrl.TrimEnd("/")
$ApiBaseUrl = $ApiBaseUrl.TrimEnd("/")

$script:Results = @()

function Add-Result {
  param(
    [string]$Name,
    [ValidateSet("PASS", "WARN", "FAIL")]
    [string]$Status,
    [string]$Details
  )

  $script:Results += [pscustomobject]@{
    Check = $Name
    Status = $Status
    Details = $Details
  }
}

function Test-PublicUrl {
  param(
    [string]$Name,
    [string]$Url
  )

  try {
    $response = Invoke-WebRequest -Uri $Url -Method Get -MaximumRedirection 5 -TimeoutSec 15
    if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400) {
      Add-Result $Name "PASS" "HTTP $($response.StatusCode)"
    } else {
      Add-Result $Name "FAIL" "HTTP $($response.StatusCode)"
    }
  }
  catch {
    Add-Result $Name "FAIL" $_.Exception.Message
  }
}

function Invoke-ProtectedGet {
  param(
    [string]$Name,
    [string]$Path,
    [hashtable]$Headers
  )

  try {
    $null = Invoke-RestMethod -Uri "$ApiBaseUrl$Path" -Method Get -Headers $Headers -TimeoutSec 20
    Add-Result $Name "PASS" "GET $Path"
    return $true
  }
  catch {
    $message = $_.Exception.Message
    if ($_.ErrorDetails.Message) {
      $message = "$message | $($_.ErrorDetails.Message)"
    }
    Add-Result $Name "FAIL" $message
    return $false
  }
}

function Read-PlainPassword {
  $secure = Read-Host "E2E password" -AsSecureString
  $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
  try {
    return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
  }
  finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
  }
}

Write-Host ""
Write-Host "DIAGLOB E2E PREFLIGHT" -ForegroundColor Cyan
Write-Host "Web: $WebBaseUrl"
Write-Host "API: $ApiBaseUrl"
Write-Host ""

Test-PublicUrl "Landing" "$WebBaseUrl/"
Test-PublicUrl "Login" "$WebBaseUrl/login"
Test-PublicUrl "Register" "$WebBaseUrl/register"
Test-PublicUrl "Privacy" "$WebBaseUrl/privacy"
Test-PublicUrl "Terms" "$WebBaseUrl/terms"
Test-PublicUrl "Refund policy" "$WebBaseUrl/refund-policy"
Test-PublicUrl "API root" "$ApiBaseUrl/"

try {
  $health = Invoke-RestMethod -Uri "$ApiBaseUrl/health" -Method Get -TimeoutSec 15
  if ($health.status -eq "ok" -and $health.database -eq "connected") {
    Add-Result "API health + database" "PASS" "status=$($health.status), database=$($health.database)"
  }
  else {
    Add-Result "API health + database" "FAIL" "status=$($health.status), database=$($health.database)"
  }
}
catch {
  Add-Result "API health + database" "FAIL" $_.Exception.Message
}

if (-not $PublicOnly) {
  if ([string]::IsNullOrWhiteSpace($Email)) {
    Add-Result "Authenticated checks" "WARN" "Set E2E_EMAIL or pass -Email to run safe authenticated smoke checks."
  }
  else {
    if ([string]::IsNullOrWhiteSpace($Password)) {
      $Password = Read-PlainPassword
    }

    try {
      $cognitoBody = @{
        AuthFlow = "USER_PASSWORD_AUTH"
        ClientId = $CognitoClientId
        AuthParameters = @{
          USERNAME = $Email.Trim().ToLowerInvariant()
          PASSWORD = $Password
        }
      } | ConvertTo-Json -Depth 6

      $cognitoHeaders = @{
        "Content-Type" = "application/x-amz-json-1.1"
        "X-Amz-Target" = "AWSCognitoIdentityProviderService.InitiateAuth"
      }

      $auth = Invoke-RestMethod -Uri "https://cognito-idp.$AwsRegion.amazonaws.com/" -Method Post -Headers $cognitoHeaders -Body $cognitoBody -TimeoutSec 20
      $accessToken = $auth.AuthenticationResult.AccessToken

      if ([string]::IsNullOrWhiteSpace($accessToken)) {
        throw "Cognito returned no AccessToken."
      }

      Add-Result "Cognito login" "PASS" "Authenticated test account; token not printed."

      $headers = @{
        Authorization = "Bearer $accessToken"
      }

      if (-not [string]::IsNullOrWhiteSpace($OrganizationId)) {
        $headers["X-Organization-Id"] = $OrganizationId
      }

      $null = Invoke-ProtectedGet "Current user" "/api/me" $headers
      $null = Invoke-ProtectedGet "Organization context" "/api/organization" $headers

      try {
        $stores = Invoke-RestMethod -Uri "$ApiBaseUrl/api/stores" -Method Get -Headers $headers -TimeoutSec 20
        Add-Result "Store list" "PASS" "$($stores.total) active store(s)"

        $effectiveStoreId = $StoreId
        if ([string]::IsNullOrWhiteSpace($effectiveStoreId) -and $stores.items -and $stores.items.Count -gt 0) {
          $effectiveStoreId = [string]$stores.items[0].id
        }

        if ([string]::IsNullOrWhiteSpace($effectiveStoreId)) {
          Add-Result "Store-scoped smoke" "WARN" "No active store found. Create/select the dedicated E2E store before testing store-scoped flows."
        }
        else {
          $storeHeaders = @{}
          foreach ($key in $headers.Keys) {
            $storeHeaders[$key] = $headers[$key]
          }
          $storeHeaders["X-Store-Id"] = $effectiveStoreId

          $null = Invoke-ProtectedGet "Operations summary" "/api/stores/$effectiveStoreId/operations/summary" $storeHeaders
          $null = Invoke-ProtectedGet "Commerce summary" "/api/stores/$effectiveStoreId/commerce/summary" $storeHeaders
          $null = Invoke-ProtectedGet "Analytics summary" "/api/stores/$effectiveStoreId/analytics/summary" $storeHeaders
          $null = Invoke-ProtectedGet "Automation flows" "/api/stores/$effectiveStoreId/automation-flows" $storeHeaders
          $null = Invoke-ProtectedGet "Authorized AI tools" "/api/ai/tools" $storeHeaders
        }
      }
      catch {
        $message = $_.Exception.Message
        if ($_.ErrorDetails.Message) {
          $message = "$message | $($_.ErrorDetails.Message)"
        }
        Add-Result "Store list" "FAIL" $message
      }
    }
    catch {
      $message = $_.Exception.Message
      if ($_.ErrorDetails.Message) {
        $message = "$message | $($_.ErrorDetails.Message)"
      }
      Add-Result "Cognito login" "FAIL" $message
    }
    finally {
      $Password = $null
      $accessToken = $null
    }
  }
}

Write-Host ""
$script:Results | Format-Table -AutoSize

$failures = @($script:Results | Where-Object { $_.Status -eq "FAIL" })
$warnings = @($script:Results | Where-Object { $_.Status -eq "WARN" })

Write-Host ""
Write-Host "Summary: $($script:Results.Count) checks, $($failures.Count) failure(s), $($warnings.Count) warning(s)."

if ($failures.Count -gt 0) {
  exit 1
}

exit 0

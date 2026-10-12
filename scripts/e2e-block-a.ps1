# Diaglob Block A: authenticated, read-only E2E smoke.
# Never prints credentials, tokens, customer data, or full response bodies.
# Requires dedicated reviewer E2E credentials; missing credentials FAIL.
param(
  [string]$ApiBaseUrl = $(if ($env:E2E_API_URL) { $env:E2E_API_URL } else { "https://api.diaglob.tech" }),
  [string]$AccessToken = $env:E2E_ACCESS_TOKEN,
  [string]$Email = $env:E2E_EMAIL,
  [string]$Password = $env:E2E_PASSWORD,
  [string]$OrganizationId = $env:E2E_ORGANIZATION_ID,
  [string]$StoreId = $env:E2E_STORE_ID,
  [string]$AwsRegion = $(if ($env:E2E_AWS_REGION) { $env:E2E_AWS_REGION } else { "us-east-2" }),
  [string]$CognitoClientId = $(if ($env:E2E_COGNITO_CLIENT_ID) { $env:E2E_COGNITO_CLIENT_ID } else { "7gas2mvvovukjpk05jhbku4303" }),
  [string]$ReportPath = $env:E2E_REPORT_PATH
)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$ApiBaseUrl = $ApiBaseUrl.TrimEnd("/")
$script:Checks = [System.Collections.Generic.List[object]]::new()

function Add-Check {
  param([string]$Name, [ValidateSet("PASS","WARN","FAIL")][string]$Status, [string]$Detail)
  $script:Checks.Add([pscustomobject]@{ check=$Name; status=$Status; detail=$Detail })
}

function Get-Api {
  param([string]$Path, [hashtable]$Headers = @{})
  try {
    $body = Invoke-RestMethod -Method Get -Uri "$ApiBaseUrl$Path" -Headers $Headers -TimeoutSec 25 -ErrorAction Stop
    return [pscustomobject]@{ ok=$true; code=200; body=$body }
  } catch {
    $code = 0
    if ($null -ne $_.Exception.Response) {
      try { $code = [int]$_.Exception.Response.StatusCode } catch { $code = 0 }
    }
    return [pscustomobject]@{ ok=$false; code=$code; body=$null }
  }
}

function Required-Get {
  param([string]$Name, [string]$Path, [hashtable]$Headers)
  $response = Get-Api -Path $Path -Headers $Headers
  if ($response.ok) { Add-Check $Name "PASS" "HTTP 200" }
  else { Add-Check $Name "FAIL" "HTTP $($response.code)" }
  return $response
}

function Finish {
  Write-Host "DIAGLOB BLOCK A AUTHENTICATED READ-ONLY E2E"
  $script:Checks | Format-Table -AutoSize
  $fails = @($script:Checks | Where-Object { $_.status -eq "FAIL" })
  $warns = @($script:Checks | Where-Object { $_.status -eq "WARN" })
  Write-Host "$($script:Checks.Count) checks; $($fails.Count) failures; $($warns.Count) warnings"
  if ($ReportPath) { $script:Checks | ConvertTo-Json -Depth 3 | Set-Content -Path $ReportPath -Encoding utf8 }
  if ($fails.Count -gt 0) { exit 1 }
  if ($warns.Count -gt 0) { exit 2 }
  exit 0
}

$health = Get-Api "/health"
if ($health.ok -and $health.body.status -eq "ok") {
  Add-Check "API health" "PASS" "Healthy"
} else {
  Add-Check "API health" "FAIL" "HTTP $($health.code) or unhealthy response"
}

if (-not $AccessToken) {
  if (-not $Email -or -not $Password) {
    Add-Check "Reviewer login" "FAIL" "Missing E2E_ACCESS_TOKEN or E2E_EMAIL + E2E_PASSWORD; authenticated E2E not executed"
    Finish
  }
  try {
    $body = @{ AuthFlow="USER_PASSWORD_AUTH"; ClientId=$CognitoClientId; AuthParameters=@{ USERNAME=$Email.Trim().ToLowerInvariant(); PASSWORD=$Password } } | ConvertTo-Json -Depth 6
    $auth = Invoke-RestMethod -Method Post -Uri "https://cognito-idp.$AwsRegion.amazonaws.com/" -Headers @{ "Content-Type"="application/x-amz-json-1.1"; "X-Amz-Target"="AWSCognitoIdentityProviderService.InitiateAuth" } -Body $body -TimeoutSec 25 -ErrorAction Stop
    $AccessToken = [string]$auth.AuthenticationResult.AccessToken
    if (-not $AccessToken) { throw "No access token" }
    Add-Check "Reviewer login" "PASS" "Cognito authenticated; token redacted"
  } catch {
    Add-Check "Reviewer login" "FAIL" "Cognito authentication failed; response redacted"
    Finish
  }
}
$Email=$null; $Password=$null
$rootHeaders = @{ Authorization="Bearer $AccessToken" }
$me = Required-Get "Current user" "/api/me" $rootHeaders
$member = Required-Get "Organization memberships" "/api/me/organizations" $rootHeaders
if (-not $me.ok -or -not $member.ok) { Finish }
$organizations = @($member.body.items | Where-Object { $null -ne $_ })
if ($organizations.Count -eq 0) {
  Add-Check "Organization membership" "FAIL" "No active membership for reviewer"
  Finish
}
if (-not $OrganizationId) {
  $OrganizationId = [string]$organizations[0].id
  if ($organizations.Count -gt 1) {
    Add-Check "Organization selection" "WARN" "Multiple memberships; set E2E_ORGANIZATION_ID"
  }
}
$chosen = @($organizations | Where-Object { [string]$_.id -eq $OrganizationId })
if ($chosen.Count -ne 1) {
  Add-Check "Organization membership" "FAIL" "Requested organization not assigned to reviewer"
  Finish
}
Add-Check "Organization selection" "PASS" "Authorized tenant selected"
$headers = @{ Authorization="Bearer $AccessToken"; "X-Organization-Id"=$OrganizationId }
$org = Required-Get "Organization summary" "/api/organization" $headers
$stores = Required-Get "Store list" "/api/stores" $headers
if (-not $org.ok -or -not $stores.ok) { Finish }
if ([string]$org.body.id -ne $OrganizationId) {
  Add-Check "Tenant context" "FAIL" "Organization ID mismatch"
  Finish
}
$items = @($stores.body.items | Where-Object { $null -ne $_ })
$active = @($items | Where-Object { $_.active -eq $true })
$orgActive = [int]$org.body.active_stores
$allStores = [bool]$org.body.all_stores
if ($items.Count -ne [int]$stores.body.total -or $items.Count -ne $active.Count) {
  Add-Check "Store consistency" "FAIL" "Store total or active filter inconsistent"
} else {
  Add-Check "Store consistency" "PASS" "$($items.Count) authorized active stores"
}
if ($items.Count -eq 0) {
  if ($orgActive -eq 0) {
    Add-Check "Sin tienda root cause" "WARN" "Organization has no active stores"
  } elseif (-not $allStores) {
    Add-Check "Sin tienda root cause" "WARN" "Active stores exist, but reviewer has no visible store assignments"
  } else {
    Add-Check "Sin tienda root cause" "FAIL" "Unrestricted reviewer cannot see existing active stores"
  }
} elseif ($items.Count -gt $orgActive) {
  Add-Check "Store membership scope" "FAIL" "Visible store count exceeds organization aggregate"
} else {
  Add-Check "Store membership scope" "PASS" "Visible stores within authorized organization aggregate"
}
$permissions = @($chosen[0].permissions)
if ($permissions -contains "agents.read") {
  $agents = Required-Get "AI Agents list" "/api/agents" $headers
  if ($agents.ok) {
    $agentRows = @($agents.body.items | Where-Object { $null -ne $_ })
    $outside = @($agentRows | Where-Object { [string]$_.organization_id -ne $OrganizationId })
    if ($outside.Count -gt 0) { Add-Check "AI Agents isolation" "FAIL" "Foreign tenant agent found" }
    else { Add-Check "AI Agents isolation" "PASS" "$($agentRows.Count) organization-scoped agents" }
  }
} else {
  Add-Check "AI Agents permissions" "WARN" "Reviewer does not have agents.read"
}
$workforce = Required-Get "AI workforce catalog" "/api/ai/workforce" $headers
if ($workforce.ok) {
  if ([string]$workforce.body.organization_id -ne $OrganizationId) { Add-Check "AI workforce scope" "FAIL" "Tenant mismatch" }
  else { Add-Check "AI workforce scope" "PASS" "Roles from selected organization" }
}
if ($permissions -contains "conversations.read") {
  $inbox = Required-Get "Unified Inbox" "/api/conversations" $headers
  if ($inbox.ok) {
    $rows = @($inbox.body.items | Where-Object { $null -ne $_ })
    $authorizedIds = @($active | ForEach-Object { [string]$_.id })
    $otherTenant = @($rows | Where-Object {
      ([string]$_.organization_id -ne $OrganizationId) -or ($authorizedIds -notcontains [string]$_.store.id)
    })
    if ($otherTenant.Count -gt 0) { Add-Check "Unified Inbox isolation" "FAIL" "Conversation from unassigned store or tenant" }
    else { Add-Check "Unified Inbox isolation" "PASS" "$($rows.Count) permitted conversation(s)" }
    foreach ($store in @($active | Select-Object -First 2)) {
      $scoped = @{ Authorization="Bearer $AccessToken"; "X-Organization-Id"=$OrganizationId; "X-Store-Id"=[string]$store.id }
      $specific = Required-Get "Store $($store.id) Inbox" "/api/conversations" $scoped
      if ($specific.ok) {
        $wrong = @($specific.body.items | Where-Object { [string]$_.store.id -ne [string]$store.id })
        if ($wrong.Count -gt 0) { Add-Check "Store-scoped Inbox" "FAIL" "Response contains another store" }
        else { Add-Check "Store-scoped Inbox" "PASS" "Store $($store.id) isolated" }
      }
    }
    if ($rows.Count -gt 0) {
      $sample = $rows[0]
      $detail = Required-Get "Conversation detail" "/api/conversations/$($sample.id)" $headers
      if ($detail.ok) {
        if ([string]$detail.body.id -ne [string]$sample.id -or
          [string]$detail.body.organization_id -ne $OrganizationId -or
          [string]$detail.body.store.id -ne [string]$sample.store.id) {
          Add-Check "Conversation detail isolation" "FAIL" "ID or tenant mismatch"
        } else { Add-Check "Conversation detail isolation" "PASS" "Detail correctly scoped; customer PII not logged" }
      }
    } else {
      Add-Check "Conversation detail" "WARN" "No conversation to validate detail; writes deliberately omitted"
    }
  }
} else {
  Add-Check "Conversations permissions" "WARN" "Reviewer does not have conversations.read"
}
if ($StoreId) {
  $selected = @($active | Where-Object { [string]$_.id -eq $StoreId })
  if ($selected.Count -ne 1) { Add-Check "Dedicated test store" "FAIL" "E2E_STORE_ID not in authorized active stores" }
  else { Add-Check "Dedicated test store" "PASS" "Authorized active test store" }
}
if ($active.Count -gt 0) {
  $target = if ($StoreId) { $StoreId } else { [string]$active[0].id }
  if (@($active | Where-Object { [string]$_.id -eq $target }).Count -eq 1) {
    $tools = Required-Get "AI tools scope" "/api/ai/tools?store_id=$target" $headers
    if ($tools.ok -and [string]$tools.body.store_id -ne $target) {
      Add-Check "AI tools isolation" "FAIL" "Tool store ID mismatch"
    }
  }
}
# Application requests above are GET only. No live customer messages or agent writes.
$AccessToken = $null
Finish

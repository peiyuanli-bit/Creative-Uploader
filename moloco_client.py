"""
Moloco Ads API Client — Complete Implementation
Covers ALL Campaign Management API endpoints:
  Auth, AdAccounts, Products, TrackingLinks, Creatives, CreativeGroups,
  Campaigns, AdGroups, AudienceTargets, CustomerSets, Reports, Logs,
  CreativeAssets, CampaignOverviews
"""

import asyncio
import certifi
import httpx
import json
import os
import ssl
import time
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta


def _detect_corporate_proxy() -> bool:
    """Detect if we're behind a corporate SSL proxy (Zscaler etc.).

    Corporate proxies like Zscaler MITM SSL connections with their own CA cert.
    These certs are often technically non-compliant (e.g. Basic Constraints not
    marked critical), which causes Python 3.13+ to reject them even when bundled.
    When detected, we disable SSL verification since the proxy is already
    terminating SSL by design.
    """
    home = Path.home()
    for indicator in [
        os.environ.get("SSL_CERT_FILE", ""),
        str(home / "zcert" / "zscaler.pem"),
        str(home / ".certs" / "zscaler.pem"),
    ]:
        if indicator and Path(indicator).is_file():
            return True
    # Check for Zscaler app or running process
    if Path("/Applications/Zscaler").is_dir():
        return True
    try:
        import subprocess
        result = subprocess.run(
            ["pgrep", "-x", "Zscaler"], capture_output=True, timeout=2,
        )
        if result.returncode == 0:
            return True
    except Exception:
        pass
    return False


def _ssl_verify():
    """Return the appropriate SSL verify parameter for httpx.

    Returns certifi's CA bundle for normal environments,
    or False for corporate proxy environments where the proxy's
    non-compliant CA cert breaks Python's strict SSL validation.
    """
    if _detect_corporate_proxy():
        return False
    return certifi.where()


class MolocoAPIClient:
    """Complete async Moloco Ads API client."""

    BASE_URL = "https://api.moloco.cloud/cm/v1"
    TOKEN_LIFETIME_HOURS = 16

    def __init__(self, api_key: str, workplace_name: str = "default"):
        self.api_key = api_key
        self.workplace_name = workplace_name
        self.access_token: Optional[str] = None
        self.token_expires_at: Optional[datetime] = None
        self._auth_lock = asyncio.Lock()
        self.client = httpx.AsyncClient(timeout=60.0, verify=_ssl_verify())

    async def close(self):
        await self.client.aclose()

    # ── Authentication ───────────────────────────────────────────────
    async def ensure_authenticated(self):
        async with self._auth_lock:
            if self.access_token and self.token_expires_at:
                if datetime.now() < self.token_expires_at - timedelta(minutes=5):
                    return
        resp = await self.client.post(
            f"{self.BASE_URL}/auth/tokens",
            json={"api_key": self.api_key},
            headers={"Content-Type": "application/json"},
        )
        if resp.status_code >= 400:
            try:
                error_body = resp.json()
            except Exception:
                error_body = resp.text
            raise Exception(f"HTTP {resp.status_code}: {error_body}")
        data = resp.json()
        self.access_token = data["token"]
        self.token_expires_at = datetime.now() + timedelta(hours=self.TOKEN_LIFETIME_HOURS)

    async def _headers(self) -> Dict[str, str]:
        await self.ensure_authenticated()
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    async def _request(self, method: str, path: str, *,
                       params: Optional[Dict] = None,
                       json_body: Optional[Any] = None,
                       data: Optional[bytes] = None,
                       extra_headers: Optional[Dict] = None) -> Dict:
        headers = await self._headers()
        if extra_headers:
            headers.update(extra_headers)
        url = f"{self.BASE_URL}/{path.lstrip('/')}"
        resp = await self.client.request(
            method, url,
            headers=headers,
            params=params,
            json=json_body,
            content=data,
        )
        if resp.status_code >= 400:
            try:
                error_body = resp.json()
            except Exception:
                error_body = resp.text
            raise Exception(f"HTTP {resp.status_code}: {error_body}")
        return resp.json() if resp.content else {}

    # Helper for standard pagination params
    @staticmethod
    def _page_params(page_size: int = 50, page_token: Optional[str] = None) -> Dict:
        p: Dict[str, Any] = {"page_size": page_size}
        if page_token:
            p["page_token"] = page_token
        return p

    # ── Ad Accounts ──────────────────────────────────────────────────
    async def list_ad_accounts(self, page_token: Optional[str] = None) -> Dict:
        return await self._request("GET", "/ad-accounts",
                                   params=self._page_params(page_token=page_token))

    async def get_ad_account(self, ad_account_id: str) -> Dict:
        return await self._request("GET", f"/ad-accounts/{ad_account_id}")

    async def create_ad_account(self, body: Dict) -> Dict:
        return await self._request("POST", "/ad-accounts", json_body=body)

    async def update_ad_account(self, ad_account_id: str, body: Dict) -> Dict:
        return await self._request("PUT", f"/ad-accounts/{ad_account_id}", json_body=body)

    async def delete_ad_account(self, ad_account_id: str) -> Dict:
        return await self._request("DELETE", f"/ad-accounts/{ad_account_id}")

    # ── Products ─────────────────────────────────────────────────────
    async def list_products(self, ad_account_id: str, page_token: Optional[str] = None) -> Dict:
        return await self._request("GET", "/products",
                                   params={"ad_account_id": ad_account_id,
                                           **self._page_params(page_token=page_token)})

    async def get_product(self, product_id: str, ad_account_id: str) -> Dict:
        return await self._request("GET", f"/products/{product_id}",
                                   params={"ad_account_id": ad_account_id})

    async def create_product(self, ad_account_id: str, body: Dict) -> Dict:
        return await self._request("POST", "/products",
                                   params={"ad_account_id": ad_account_id},
                                   json_body=body)

    async def update_product(self, product_id: str, ad_account_id: str, body: Dict) -> Dict:
        return await self._request("PUT", f"/products/{product_id}",
                                   params={"ad_account_id": ad_account_id},
                                   json_body=body)

    async def delete_product(self, product_id: str, ad_account_id: str) -> Dict:
        return await self._request("DELETE", f"/products/{product_id}",
                                   params={"ad_account_id": ad_account_id})

    # ── Tracking Links ───────────────────────────────────────────────
    async def list_tracking_links(self, ad_account_id: str, product_id: str,
                                  page_token: Optional[str] = None) -> Dict:
        return await self._request("GET", "/tracking-links",
                                   params={"ad_account_id": ad_account_id,
                                           "product_id": product_id,
                                           **self._page_params(page_token=page_token)})

    async def get_tracking_link(self, tracking_link_id: str,
                                ad_account_id: str, product_id: str) -> Dict:
        return await self._request("GET", f"/tracking-links/{tracking_link_id}",
                                   params={"ad_account_id": ad_account_id,
                                           "product_id": product_id})

    async def create_tracking_link(self, ad_account_id: str, product_id: str,
                                   body: Dict) -> Dict:
        return await self._request("POST", "/tracking-links",
                                   params={"ad_account_id": ad_account_id,
                                           "product_id": product_id},
                                   json_body=body)

    async def update_tracking_link(self, tracking_link_id: str,
                                   ad_account_id: str, product_id: str,
                                   body: Dict) -> Dict:
        return await self._request("PUT", f"/tracking-links/{tracking_link_id}",
                                   params={"ad_account_id": ad_account_id,
                                           "product_id": product_id},
                                   json_body=body)

    async def delete_tracking_link(self, tracking_link_id: str,
                                   ad_account_id: str, product_id: str) -> Dict:
        return await self._request("DELETE", f"/tracking-links/{tracking_link_id}",
                                   params={"ad_account_id": ad_account_id,
                                           "product_id": product_id})

    # ── Creative Assets (Upload to GCS) ──────────────────────────────
    async def create_asset_upload_session(self, ad_account_id: str,
                                         asset_kind: str = "CREATIVE",
                                         mime_type: str = "image/jpeg") -> Dict:
        return await self._request("POST", "/creative-assets",
                                   params={"ad_account_id": ad_account_id},
                                   json_body={"asset_kind": asset_kind,
                                              "mime_type": mime_type})

    async def upload_asset_to_gcs(self, upload_url: str, file_bytes: bytes,
                                  content_type: str = "image/jpeg") -> int:
        """PUT binary data to the GCS upload URL. Returns HTTP status."""
        resp = await self.client.put(
            upload_url,
            content=file_bytes,
            headers={"Content-Type": content_type},
        )
        if resp.status_code >= 400:
            try:
                error_body = resp.json()
            except Exception:
                error_body = resp.text
            raise Exception(f"HTTP {resp.status_code}: {error_body}")
        return resp.status_code

    # ── Creatives ────────────────────────────────────────────────────
    async def list_creatives(self, ad_account_id: str,
                             product_id: Optional[str] = None,
                             page_token: Optional[str] = None) -> Dict:
        params: Dict[str, Any] = {"ad_account_id": ad_account_id,
                                  **self._page_params(page_token=page_token)}
        if product_id:
            params["product_id"] = product_id
        return await self._request("GET", "/creatives", params=params)

    async def get_creative(self, creative_id: str, ad_account_id: str) -> Dict:
        return await self._request("GET", f"/creatives/{creative_id}",
                                   params={"ad_account_id": ad_account_id})

    async def create_creative(self, ad_account_id: str, body: Dict,
                              product_id: Optional[str] = None) -> Dict:
        params: Dict[str, Any] = {"ad_account_id": ad_account_id}
        if product_id:
            params["product_id"] = product_id
        return await self._request("POST", "/creatives",
                                   params=params, json_body=body)

    async def update_creative(self, creative_id: str, ad_account_id: str,
                              body: Dict) -> Dict:
        return await self._request("PUT", f"/creatives/{creative_id}",
                                   params={"ad_account_id": ad_account_id},
                                   json_body=body)

    async def delete_creative(self, creative_id: str, ad_account_id: str) -> Dict:
        return await self._request("DELETE", f"/creatives/{creative_id}",
                                   params={"ad_account_id": ad_account_id})

    # ── Creative Groups ──────────────────────────────────────────────
    async def list_creative_groups(self, ad_account_id: str,
                                   product_id: Optional[str] = None,
                                   page_token: Optional[str] = None) -> Dict:
        params: Dict[str, Any] = {"ad_account_id": ad_account_id,
                                  **self._page_params(page_token=page_token)}
        if product_id:
            params["product_id"] = product_id
        return await self._request("GET", "/creative-groups", params=params)

    async def get_creative_group(self, creative_group_id: str,
                                 ad_account_id: str) -> Dict:
        return await self._request("GET", f"/creative-groups/{creative_group_id}",
                                   params={"ad_account_id": ad_account_id})

    async def create_creative_group(self, ad_account_id: str, product_id: str,
                                    body: Dict) -> Dict:
        return await self._request("POST", "/creative-groups",
                                   params={"ad_account_id": ad_account_id,
                                           "product_id": product_id},
                                   json_body=body)

    async def update_creative_group(self, creative_group_id: str,
                                    ad_account_id: str, body: Dict) -> Dict:
        return await self._request("PUT", f"/creative-groups/{creative_group_id}",
                                   params={"ad_account_id": ad_account_id},
                                   json_body=body)

    async def delete_creative_group(self, creative_group_id: str,
                                    ad_account_id: str) -> Dict:
        return await self._request("DELETE", f"/creative-groups/{creative_group_id}",
                                   params={"ad_account_id": ad_account_id})

    # ── Campaigns ────────────────────────────────────────────────────
    async def list_campaigns(self, ad_account_id: str,
                             product_id: Optional[str] = None,
                             page_token: Optional[str] = None) -> Dict:
        params: Dict[str, Any] = {"ad_account_id": ad_account_id,
                                  **self._page_params(page_token=page_token)}
        if product_id:
            params["product_id"] = product_id
        return await self._request("GET", "/campaigns", params=params)

    async def get_campaign(self, campaign_id: str) -> Dict:
        return await self._request("GET", f"/campaigns/{campaign_id}")

    async def create_campaign(self, ad_account_id: str, product_id: str,
                              body: Dict) -> Dict:
        return await self._request("POST", "/campaigns",
                                   params={"ad_account_id": ad_account_id,
                                           "product_id": product_id},
                                   json_body=body)

    async def update_campaign(self, campaign_id: str, body: Dict) -> Dict:
        return await self._request("PUT", f"/campaigns/{campaign_id}",
                                   json_body=body)

    async def delete_campaign(self, campaign_id: str) -> Dict:
        return await self._request("DELETE", f"/campaigns/{campaign_id}")

    # ── Campaign Overviews ───────────────────────────────────────────
    async def query_campaign_overviews(self, ad_account_id: str,
                                       campaign_ids: Optional[List[str]] = None) -> Dict:
        params: Dict[str, Any] = {"ad_account_id": ad_account_id}
        if campaign_ids:
            params["campaign_ids"] = ",".join(campaign_ids)
        return await self._request("GET", "/campaign-overviews", params=params)

    # ── Ad Groups ────────────────────────────────────────────────────
    async def list_ad_groups(self, campaign_id: str,
                             ad_account_id: Optional[str] = None,
                             page_token: Optional[str] = None) -> Dict:
        params: Dict[str, Any] = {"campaign_id": campaign_id,
                                  **self._page_params(page_token=page_token)}
        if ad_account_id:
            params["ad_account_id"] = ad_account_id
        return await self._request("GET", "/ad-groups", params=params)

    async def get_ad_group(self, ad_group_id: str, campaign_id: str,
                           ad_account_id: Optional[str] = None) -> Dict:
        params: Dict[str, Any] = {"campaign_id": campaign_id}
        if ad_account_id:
            params["ad_account_id"] = ad_account_id
        return await self._request("GET", f"/ad-groups/{ad_group_id}",
                                   params=params)

    async def create_ad_group(self, campaign_id: str, body: Dict,
                              ad_account_id: Optional[str] = None) -> Dict:
        params: Dict[str, Any] = {"campaign_id": campaign_id}
        if ad_account_id:
            params["ad_account_id"] = ad_account_id
        return await self._request("POST", "/ad-groups",
                                   params=params, json_body=body)

    async def update_ad_group(self, ad_group_id: str, campaign_id: str,
                              body: Dict, ad_account_id: Optional[str] = None) -> Dict:
        params: Dict[str, Any] = {"campaign_id": campaign_id}
        if ad_account_id:
            params["ad_account_id"] = ad_account_id
        return await self._request("PUT", f"/ad-groups/{ad_group_id}",
                                   params=params, json_body=body)

    async def delete_ad_group(self, ad_group_id: str, campaign_id: str,
                              ad_account_id: Optional[str] = None) -> Dict:
        params: Dict[str, Any] = {"campaign_id": campaign_id}
        if ad_account_id:
            params["ad_account_id"] = ad_account_id
        return await self._request("DELETE", f"/ad-groups/{ad_group_id}",
                                   params=params)

    # ── Audience Targets ─────────────────────────────────────────────
    async def list_audience_targets(self, ad_account_id: str,
                                    page_token: Optional[str] = None) -> Dict:
        return await self._request("GET", "/audience-targets",
                                   params={"ad_account_id": ad_account_id,
                                           **self._page_params(page_token=page_token)})

    async def get_audience_target(self, audience_target_id: str,
                                  ad_account_id: str) -> Dict:
        return await self._request("GET", f"/audience-targets/{audience_target_id}",
                                   params={"ad_account_id": ad_account_id})

    async def create_audience_target(self, ad_account_id: str, body: Dict) -> Dict:
        return await self._request("POST", "/audience-targets",
                                   params={"ad_account_id": ad_account_id},
                                   json_body=body)

    async def update_audience_target(self, audience_target_id: str,
                                     ad_account_id: str, body: Dict) -> Dict:
        return await self._request("PUT", f"/audience-targets/{audience_target_id}",
                                   params={"ad_account_id": ad_account_id},
                                   json_body=body)

    async def delete_audience_target(self, audience_target_id: str,
                                     ad_account_id: str) -> Dict:
        return await self._request("DELETE", f"/audience-targets/{audience_target_id}",
                                   params={"ad_account_id": ad_account_id})

    # ── Customer Sets ────────────────────────────────────────────────
    async def list_customer_sets(self, ad_account_id: str,
                                 page_token: Optional[str] = None) -> Dict:
        return await self._request("GET", "/customer-sets",
                                   params={"ad_account_id": ad_account_id,
                                           **self._page_params(page_token=page_token)})

    async def get_customer_set(self, customer_set_id: str,
                               ad_account_id: str) -> Dict:
        return await self._request("GET", f"/customer-sets/{customer_set_id}",
                                   params={"ad_account_id": ad_account_id})

    async def create_customer_set(self, ad_account_id: str, body: Dict) -> Dict:
        return await self._request("POST", "/customer-sets",
                                   params={"ad_account_id": ad_account_id},
                                   json_body=body)

    async def update_customer_set(self, customer_set_id: str,
                                  ad_account_id: str, body: Dict) -> Dict:
        return await self._request("PUT", f"/customer-sets/{customer_set_id}",
                                   params={"ad_account_id": ad_account_id},
                                   json_body=body)

    async def delete_customer_set(self, customer_set_id: str,
                                  ad_account_id: str) -> Dict:
        return await self._request("DELETE", f"/customer-sets/{customer_set_id}",
                                   params={"ad_account_id": ad_account_id})

    # ── Reports ──────────────────────────────────────────────────────
    async def list_reports(self, page_token: Optional[str] = None) -> Dict:
        return await self._request("GET", "/reports",
                                   params=self._page_params(page_token=page_token))

    async def get_report(self, report_id: str) -> Dict:
        return await self._request("GET", f"/reports/{report_id}")

    async def create_report(self, body: Dict) -> Dict:
        return await self._request("POST", "/reports", json_body=body)

    async def get_report_status(self, report_id: str) -> Dict:
        return await self._request("GET", f"/reports/{report_id}/status")

    async def delete_report(self, report_id: str) -> Dict:
        return await self._request("DELETE", f"/reports/{report_id}")

    async def download_report(self, url: str) -> Any:
        """Download report data from the GCS signed URL returned in report status.

        IMPORTANT: The URL is a pre-signed GCS URL from Moloco. Do NOT add
        any auth headers — the signature already encodes the access grant.
        Adding extra headers (like Authorization) causes SignatureDoesNotMatch.
        """
        resp = await self.client.get(url, follow_redirects=True)
        if resp.status_code >= 400:
            try:
                error_body = resp.json()
            except Exception:
                error_body = resp.text
            raise Exception(f"HTTP {resp.status_code}: {error_body}")
        try:
            return resp.json()
        except Exception:
            return resp.text

    async def download_from_signed_url(self, url: str) -> Any:
        """Download data from any pre-signed GCS URL (reports, logs, etc.).

        Same as download_report — no auth headers, the URL is self-authenticating.
        """
        return await self.download_report(url)

    # ── Logs ─────────────────────────────────────────────────────────
    async def list_logs(self, ad_account_id: str,
                        page_token: Optional[str] = None) -> Dict:
        return await self._request("GET", "/logs",
                                   params={"ad_account_id": ad_account_id,
                                           **self._page_params(page_token=page_token)})

    async def get_log(self, log_id: str) -> Dict:
        return await self._request("GET", f"/logs/{log_id}")

    async def create_log(self, ad_account_id: str, body: Dict) -> Dict:
        return await self._request("POST", "/logs",
                                   params={"ad_account_id": ad_account_id},
                                   json_body=body)

    async def get_log_status(self, log_id: str) -> Dict:
        return await self._request("GET", f"/logs/{log_id}/status")

    async def delete_log(self, log_id: str) -> Dict:
        return await self._request("DELETE", f"/logs/{log_id}")

"""ApifyInstagramSource

Fetches public Instagram profile data via Apify's Instagram Profile Scraper.
Only public data is collected — no authentication, no private accounts.

Legal basis: Apify fetches the same information visible to any anonymous
browser visiting instagram.com/<username>. Profile data (bio, follower count,
account type) is public by default and does not require login to view.

Activation: set APIFY_TOKEN and INSTAGRAM_USERNAMES in environment.
When APIFY_TOKEN is absent the source silently returns [] (no-op).

Apify actor used: apify/instagram-profile-scraper
Docs: https://apify.com/apify/instagram-profile-scraper
"""
import logging

import httpx

from services.scraper.sources.base import BaseSource, RawLead

log = logging.getLogger(__name__)

APIFY_RUN_URL = "https://api.apify.com/v2/acts/apify~instagram-profile-scraper/runs"


class ApifyInstagramSource(BaseSource):
    """Collects public Instagram profile data for lead generation.

    Maps profile fields to RawLead so the rest of the pipeline treats
    Instagram leads exactly like any other source.
    """

    source_name = "instagram"

    def __init__(self, token: str, usernames: list[str]) -> None:
        self._token = token
        self._usernames = usernames
        self._client = httpx.AsyncClient(timeout=120.0)

    @property
    def source_name(self) -> str:  # type: ignore[override]
        return "instagram"

    async def fetch(self) -> list[RawLead]:
        if not self._usernames:
            return []

        try:
            return await self._run_actor()
        except Exception:
            log.exception("Apify Instagram fetch failed")
            return []

    async def _run_actor(self) -> list[RawLead]:
        headers = {"Authorization": f"Bearer {self._token}"}

        # Start synchronous run (waits for completion, max 5 min via timeout)
        resp = await self._client.post(
            f"{APIFY_RUN_URL}?waitForFinish=300",
            headers=headers,
            json={"usernames": self._usernames},
        )
        resp.raise_for_status()
        run_data = resp.json()

        dataset_id = run_data["data"]["defaultDatasetId"]
        items_resp = await self._client.get(
            f"https://api.apify.com/v2/datasets/{dataset_id}/items",
            headers=headers,
            params={"format": "json", "clean": "true"},
        )
        items_resp.raise_for_status()
        profiles = items_resp.json()

        leads: list[RawLead] = []
        for profile in profiles:
            lead = self._profile_to_raw_lead(profile)
            if lead:
                leads.append(lead)

        log.info("Apify Instagram fetched profiles", count=len(leads))
        return leads

    def _profile_to_raw_lead(self, profile: dict) -> RawLead | None:
        username = profile.get("username") or profile.get("inputUrl", "").split("/")[-1]
        if not username:
            return None

        # Use business email if available (public contact info on business accounts)
        email = profile.get("businessEmail") or profile.get("publicEmail") or f"{username}@instagram.invalid"
        name = profile.get("fullName") or username
        biography = profile.get("biography") or profile.get("bio") or ""

        # Engagement rate: apify may provide it or we compute a rough estimate
        followers = profile.get("followersCount") or 0
        following = profile.get("followingCount") or 0
        posts = profile.get("postsCount") or 0
        engagement_rate: float | None = profile.get("engagementRate")
        account_type = profile.get("accountType") or ("business" if profile.get("isBusinessAccount") else "personal")
        profile_url = f"https://www.instagram.com/{username}/"

        return RawLead(
            name=name,
            email=email,
            phone=profile.get("businessPhoneNumber"),
            company=profile.get("businessCategoryName"),
            extra={
                "instagram_username": username,
                "instagram_bio": biography,
                "instagram_followers": followers,
                "instagram_following": following,
                "instagram_posts": posts,
                "instagram_engagement_rate": engagement_rate,
                "instagram_account_type": account_type,
                "instagram_profile_url": profile_url,
            },
        )

    async def close(self) -> None:
        await self._client.aclose()

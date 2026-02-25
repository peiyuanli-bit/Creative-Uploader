"""
Moloco Ads MCP Server — Shared Constants

Valid dimension sets, resize targets, goal sub-keys, and other constants
extracted from server.py for reuse across helper modules.
"""

from typing import Dict, List

# ── Valid dimension sets (for validation) ──
VALID_IMAGE_SIZES = {
    (300, 250), (320, 480), (320, 50), (728, 90),
    (480, 320), (768, 1024), (1024, 768), (300, 50), (468, 60),
}

VALID_NATIVE_SIZES = {
    (1200, 628), (1200, 600), (720, 720), (720, 960), (720, 1280), (1200, 1600),
}

# ── Resize targets (separated by creative type) ──
IMAGE_RESIZE_TARGETS = [
    {"w": 300, "h": 250, "label": "Medium Rectangle", "priority": "high", "type": "IMAGE"},
    {"w": 320, "h": 480, "label": "Portrait Interstitial", "priority": "high", "type": "IMAGE"},
    {"w": 320, "h": 50, "label": "Mobile Banner", "priority": "high", "type": "IMAGE"},
    {"w": 728, "h": 90, "label": "Leaderboard", "priority": "high", "type": "IMAGE"},
    {"w": 480, "h": 320, "label": "Landscape Interstitial", "priority": "medium", "type": "IMAGE"},
    {"w": 768, "h": 1024, "label": "Tablet Portrait", "priority": "medium", "type": "IMAGE"},
    {"w": 1024, "h": 768, "label": "Tablet Landscape", "priority": "medium", "type": "IMAGE"},
    {"w": 300, "h": 50, "label": "Mobile Banner Small", "priority": "medium", "type": "IMAGE"},
    {"w": 468, "h": 60, "label": "Banner", "priority": "medium", "type": "IMAGE"},
]

NATIVE_RESIZE_TARGETS = [
    {"w": 1200, "h": 628, "label": "Native Landscape", "priority": "high", "type": "NATIVE"},
    {"w": 720, "h": 720, "label": "Native Square", "priority": "medium", "type": "NATIVE"},
    {"w": 720, "h": 1280, "label": "Native Portrait", "priority": "medium", "type": "NATIVE"},
]

VIDEO_RESIZE_TARGETS = [
    {"w": 1920, "h": 1080, "label": "Landscape HD", "priority": "high"},
    {"w": 1080, "h": 1920, "label": "Portrait HD", "priority": "high"},
    {"w": 720, "h": 720, "label": "Square", "priority": "medium"},
    {"w": 1280, "h": 720, "label": "Landscape 720p", "priority": "medium"},
    {"w": 720, "h": 1280, "label": "Portrait 720p", "priority": "medium"},
]

# Goal type -> required sub-key for validation
GOAL_SUB_KEYS = {
    "OPTIMIZE_CPI_FOR_APP_UA": "optimize_app_installs",
    "OPTIMIZE_CPA_FOR_APP_UA": "optimize_cpa_for_app_ua",
    "OPTIMIZE_CPA_FOR_APP_RE": "optimize_cpa_for_app_re",
    "OPTIMIZE_CTV_ASSIST_FOR_APP_UA": "optimize_ctv_assist_for_app_ua",
}


def is_valid_image_dimension(w: int, h: int) -> bool:
    return (w, h) in VALID_IMAGE_SIZES


def is_valid_native_dimension(w: int, h: int) -> bool:
    return (w, h) in VALID_NATIVE_SIZES


def validate_campaign_data(data: Dict) -> List[str]:
    """Pre-validate campaign creation data and return a list of warnings/errors."""
    warnings = []
    campaign = data.get("campaign", data)

    # Check for common country mistake
    if "country" in campaign and "countries" not in campaign:
        warnings.append("ERROR: Use 'countries' (array like ['USA']), not 'country' (singular)")
    if "countries" in campaign and not isinstance(campaign["countries"], list):
        warnings.append("ERROR: 'countries' must be an array, e.g. ['USA']")

    # Check campaign type
    cam_type = campaign.get("type", "")
    if "RE_ENGAGEMENT" in cam_type:
        warnings.append("ERROR: Use 'APP_REENGAGEMENT' (one word), not 'APP_RE_ENGAGEMENT'")

    # Check goal structure
    goal = campaign.get("goal", {})
    goal_type = goal.get("type", "")
    expected_key = GOAL_SUB_KEYS.get(goal_type)
    if expected_key and expected_key not in goal:
        warnings.append(
            f"ERROR: Goal type '{goal_type}' requires sub-key '{expected_key}' but it's missing. "
            f"Found keys: {[k for k in goal.keys() if k != 'type']}"
        )

    # Check amount_micros is string
    budget = campaign.get("budget_schedule", {})
    for sched_key, sched_val in budget.items():
        if isinstance(sched_val, dict):
            for bkey, bval in sched_val.items():
                if isinstance(bval, dict) and "amount_micros" in bval:
                    if not isinstance(bval["amount_micros"], str):
                        warnings.append(
                            f"ERROR: amount_micros must be a STRING, got {type(bval['amount_micros']).__name__}"
                        )

    # Check RE-specific rules
    if cam_type == "APP_REENGAGEMENT":
        if campaign.get("ad_tracking_allowance") == "DO_NOT_CARE":
            warnings.append("WARNING: RE campaigns should typically use 'NON_LAT_ONLY', not 'DO_NOT_CARE'")
        ad_group = data.get("ad_group", {})
        if ad_group.get("tracking_link_id"):
            warnings.append(
                "ERROR: tracking_link_id is NOT allowed on ad_group for RE campaigns (put it on the campaign)"
            )

    # Check tracking_link_id for UA/RE
    if cam_type in ("APP_USER_ACQUISITION", "APP_REENGAGEMENT"):
        if not campaign.get("tracking_link_id"):
            warnings.append("WARNING: tracking_link_id is typically required on the campaign for UA/RE types")

    return warnings


# ═════════════════════════════════════════════════════════════════════
# Schema reference — JSON templates for creating Moloco entities
# ═════════════════════════════════════════════════════════════════════

SCHEMA_REFERENCE = {
    "campaign_ua_cpi": {
        "description": "User Acquisition campaign optimizing for Cost Per Install",
        "template": {
            "campaign": {
                "ad_account_id": "ACCOUNT_ID",
                "product_id": "PRODUCT_ID",
                "title": "Campaign Title",
                "enabling_state": "DISABLED",
                "type": "APP_USER_ACQUISITION",
                "device_os": "IOS or ANDROID",
                "countries": ["USA"],
                "currency": "USD",
                "schedule": {"start": "2026-02-08T00:00:00Z"},
                "budget_schedule": {
                    "daily_schedule": {
                        "daily_budget": {"currency": "USD", "amount_micros": "500000000"}
                    }
                },
                "tracking_company": "APPSFLYER",
                "tracking_link_id": "TRACKING_LINK_ID",
                "goal": {
                    "type": "OPTIMIZE_CPI_FOR_APP_UA",
                    "optimize_app_installs": {
                        "mode": "BUDGET_CENTRIC",
                        "rate": 1
                    }
                },
                "ad_tracking_allowance": "DO_NOT_CARE"
            },
            "ad_group": {
                "title": "Default Ad Group",
                "enabling_state": "ENABLED",
                "audience": {},
                "capper": {"imp_interval": {"amount": "12", "unit": "HOUR"}},
                "creative_group_ids": []
            }
        },
        "notes": [
            "countries must be an ARRAY like ['USA'], not singular 'country'",
            "tracking_link_id is required on the campaign",
            "amount_micros is a STRING (dollars x 1,000,000: $500 = '500000000')",
            "ad_tracking_allowance should be 'DO_NOT_CARE' for UA",
        ],
    },
    "campaign_ua_cpa": {
        "description": "User Acquisition campaign optimizing for Cost Per Action (in-app event)",
        "template": {
            "campaign": {
                "ad_account_id": "ACCOUNT_ID",
                "product_id": "PRODUCT_ID",
                "title": "Campaign Title",
                "enabling_state": "DISABLED",
                "type": "APP_USER_ACQUISITION",
                "device_os": "IOS or ANDROID",
                "countries": ["USA"],
                "currency": "USD",
                "schedule": {"start": "2026-02-08T00:00:00Z"},
                "budget_schedule": {
                    "weekly_flexible_schedule": {
                        "weekly_budget": {"currency": "USD", "amount_micros": "3500000000"}
                    }
                },
                "tracking_company": "APPSFLYER",
                "tracking_link_id": "TRACKING_LINK_ID",
                "goal": {
                    "type": "OPTIMIZE_CPA_FOR_APP_UA",
                    "optimize_cpa_for_app_ua": {
                        "action": "EVENT_NAME",
                        "mode": "BUDGET_CENTRIC",
                        "rate": 1
                    },
                    "kpi_actions": ["EVENT_NAME"]
                },
                "ad_tracking_allowance": "DO_NOT_CARE"
            },
            "ad_group": {
                "title": "Default Ad Group",
                "enabling_state": "ENABLED",
                "audience": {},
                "capper": {"imp_interval": {"amount": "12", "unit": "HOUR"}},
                "creative_group_ids": []
            }
        },
        "notes": [
            "action must match an event in the product's app_event_types",
            "kpi_actions can differ from the optimization action",
            "Common actions: bet_placed_first_time, deposit_placed_first_time, purchase",
        ],
    },
    "campaign_re": {
        "description": "Re-Engagement (retargeting) campaign",
        "template": {
            "campaign": {
                "ad_account_id": "ACCOUNT_ID",
                "product_id": "PRODUCT_ID",
                "title": "RE Campaign Title",
                "enabling_state": "DISABLED",
                "type": "APP_REENGAGEMENT",
                "device_os": "ANDROID or IOS",
                "countries": ["USA"],
                "currency": "USD",
                "schedule": {"start": "2026-02-08T00:00:00Z"},
                "budget_schedule": {
                    "weekly_flexible_schedule": {
                        "weekly_budget": {"currency": "USD", "amount_micros": "3500000000"}
                    }
                },
                "tracking_company": "APPSFLYER",
                "tracking_link_id": "TRACKING_LINK_ID",
                "goal": {
                    "type": "OPTIMIZE_CPA_FOR_APP_RE",
                    "optimize_cpa_for_app_re": {
                        "action": "EVENT_NAME",
                        "reengagement_action": "click",
                        "mode": "BUDGET_CENTRIC",
                        "rate": 1
                    }
                },
                "ad_tracking_allowance": "NON_LAT_ONLY"
            },
            "ad_group": {
                "title": "Default Ad Group",
                "enabling_state": "ENABLED",
                "audience": {},
                "capper": {"imp_interval": {"amount": "12", "unit": "HOUR"}},
                "creative_group_ids": []
            }
        },
        "notes": [
            "CRITICAL: Campaign type is APP_REENGAGEMENT (one word), NOT APP_RE_ENGAGEMENT",
            "tracking_link_id is required on the campaign but NOT allowed on the ad_group",
            "ad_tracking_allowance should be 'NON_LAT_ONLY' for RE campaigns",
            "RE tracking links need is_retargeting=true and af_reengagement_window=lifetime",
        ],
    },
    "campaign_ctv": {
        "description": "Connected TV campaign driving app installs via CTV ads",
        "template": {
            "campaign": {
                "ad_account_id": "ACCOUNT_ID",
                "product_id": "PRODUCT_ID (must be WEB type with device_os VERSATILE)",
                "title": "CTV Campaign Title",
                "enabling_state": "DISABLED",
                "type": "CTV_APP_USER_ACQUISITION",
                "device_os": "VERSATILE",
                "countries": ["USA"],
                "currency": "USD",
                "schedule": {"start": "2026-02-08T00:00:00Z"},
                "budget_schedule": {
                    "daily_schedule": {
                        "daily_budget": {"currency": "USD", "amount_micros": "500000000"}
                    }
                },
                "goal": {
                    "type": "OPTIMIZE_CTV_ASSIST_FOR_APP_UA",
                    "optimize_ctv_assist_for_app_ua": {
                        "target_app_bundles": {
                            "ANDROID": "com.example.app",
                            "IOS": "id123456789"
                        }
                    },
                    "kpi_actions": ["EVENT_NAME"]
                },
                "ad_tracking_allowance": "DO_NOT_CARE"
            },
            "ad_group": {
                "title": "Default Ad Group",
                "enabling_state": "ENABLED",
                "audience": {},
                "creative_group_ids": []
            }
        },
        "notes": [
            "Product must be type WEB with device_os VERSATILE",
            "target_app_bundles maps OS to the mobile app bundle IDs being promoted",
        ],
    },
    "creative_image": {
        "description": "Image creative (static banner ad)",
        "template": {
            "title": "offer_768x1024_static.png",
            "type": "IMAGE",
            "original_filename": "offer_768x1024_static.png",
            "size_in_bytes": 277826,
            "image": {
                "image_url": "GCS_URL_FROM_UPLOAD_SESSION",
                "filename": "offer_768x1024_static.png",
                "width": 768,
                "height": 1024,
                "size_in_bytes": 277826
            }
        },
        "notes": [
            "First create an upload session, upload the file to GCS, then use the asset_url as image_url",
        ],
    },
    "creative_video": {
        "description": "Video creative (REQUIRES companion_images / endcard)",
        "template": {
            "title": "video_1920x1080_6s.mp4",
            "type": "VIDEO",
            "original_filename": "video_1920x1080_6s.mp4",
            "size_in_bytes": 954726,
            "video": {
                "video_url": "GCS_URL_FROM_UPLOAD_SESSION",
                "filename": "video_1920x1080_6s.mp4",
                "width": 1920,
                "height": 1080,
                "length_seconds": 6,
                "size_in_bytes": 954726,
                "companion_images": [
                    {
                        "image_url": "GCS_URL_FOR_ENDCARD",
                        "filename": "endcard.png",
                        "width": 640,
                        "height": 360,
                        "size_in_bytes": 479417
                    }
                ]
            }
        },
        "notes": [
            "CRITICAL: companion_images (endcard) is REQUIRED — cannot be empty or omitted",
            "Upload both video and endcard image via separate upload sessions first",
            "Videos are auto-transcoded; returned size_in_bytes may differ from original",
        ],
    },
    "tracking_link_appsflyer": {
        "description": "AppsFlyer tracking link (acquisition)",
        "template": {
            "title": "Campaign Name - Platform",
            "device_os": "ANDROID or IOS",
            "click_through_link": {
                "url": "https://YOURAPP.onelink.me/TOKEN?advertising_id={{device.gaid}}&af_ad={{creative.title}}&af_ad_id={{creative.cr_id}}&af_ad_type={{creative.type}}&af_c_id={{campaign.id}}&af_channel=programmatic&af_click_lookback=7d&af_cost_currency={{price.cost_currency}}&af_cost_model={{price.cost_type}}&af_cost_value={{price.cost_amount}}&af_ip={{device.ip}}&af_siteid={{publisher.bundle}}&af_sub4={{mtid}}&af_ua={{device.user_agent}}&c={{campaign.title}}&clickid={{mtid}}&pid=moloco_int"
            },
            "view_through_link": {
                "url": "https://impressions.onelink.me/TOKEN?...&af_viewthrough_lookback=24h&..."
            },
            "tracking_company": "APPSFLYER"
        },
        "notes": [
            "For retargeting add: is_retargeting=true&af_reengagement_window=lifetime&af_dp=DEEPLINK_URL",
            "Tracking companies: APPSFLYER, ADJUST, BRANCH, KOCHAVA, SINGULAR, TRACKFNT",
        ],
    },
    "tracking_link_adjust": {
        "description": "Adjust tracking link",
        "template": {
            "title": "Campaign Name - Platform",
            "device_os": "ANDROID or IOS",
            "click_through_link": {
                "url": "https://app.adjust.com/TOKEN?adgroup={{publisher.bundle}}&campaign={{campaign.title}}&creative={{creative.cr_id}}&gps_adid={{device.gaid}}&molo_click_id={{mtid}}"
            },
            "view_through_link": {
                "url": "https://view.adjust.com/impression/TOKEN?..."
            },
            "tracking_company": "ADJUST"
        },
        "notes": [],
    },
    "creative_group": {
        "description": "Creative group bundling creatives with a tracking link",
        "template": {
            "title": "Creative Group Name",
            "enabling_state": "ENABLED",
            "creative_ids": ["creative_id_1", "creative_id_2"],
            "tracking_link_id": "TRACKING_LINK_ID",
            "audience": {
                "targeting_condition": {
                    "schedule": {
                        "start": "2026-02-08T00:00:00Z",
                        "end": "2026-03-01T00:00:00Z"
                    }
                }
            },
            "feature": {"type": "GENERAL"}
        },
        "notes": [
            "schedule in audience.targeting_condition is optional (controls when group is active)",
            "feature.type is typically GENERAL",
        ],
    },
    "budget_daily": {
        "description": "Fixed daily budget schedule",
        "template": {
            "daily_schedule": {
                "daily_budget": {"currency": "USD", "amount_micros": "500000000"}
            }
        },
        "notes": ["amount_micros is a STRING. Dollars x 1,000,000. $500 = '500000000'"],
    },
    "budget_weekly_flexible": {
        "description": "Weekly flexible budget (ML-optimized across days)",
        "template": {
            "weekly_flexible_schedule": {
                "weekly_budget": {"currency": "USD", "amount_micros": "3500000000"}
            }
        },
        "notes": ["ML distributes spend optimally across the week"],
    },
    "budget_weekly": {
        "description": "Fixed per-day weekly budget",
        "template": {
            "weekly_schedule": {
                "monday_budget": {"currency": "USD", "amount_micros": "500000000"},
                "tuesday_budget": {"currency": "USD", "amount_micros": "500000000"},
                "wednesday_budget": {"currency": "USD", "amount_micros": "500000000"},
                "thursday_budget": {"currency": "USD", "amount_micros": "500000000"},
                "friday_budget": {"currency": "USD", "amount_micros": "500000000"},
                "saturday_budget": {"currency": "USD", "amount_micros": "500000000"},
                "sunday_budget": {"currency": "USD", "amount_micros": "500000000"}
            }
        },
        "notes": ["Set different budgets per day of week"],
    },
    "budget_monthly_flexible": {
        "description": "Monthly flexible budget (per-month amounts)",
        "template": {
            "monthly_flexible_schedule": {
                "january_budget": {"currency": "USD", "amount_micros": "25000000000"},
                "february_budget": {"currency": "USD", "amount_micros": "25000000000"},
            }
        },
        "notes": ["Set budget for each month. All 12 months should be included."],
    },
    "goal_types": {
        "description": "All campaign goal types and their required sub-key structures",
        "template": {
            "OPTIMIZE_CPI_FOR_APP_UA": {
                "sub_key": "optimize_app_installs",
                "fields": {"mode": "BUDGET_CENTRIC", "rate": 1}
            },
            "OPTIMIZE_CPA_FOR_APP_UA": {
                "sub_key": "optimize_cpa_for_app_ua",
                "fields": {"action": "EVENT_NAME", "mode": "BUDGET_CENTRIC", "rate": 1}
            },
            "OPTIMIZE_CPA_FOR_APP_RE": {
                "sub_key": "optimize_cpa_for_app_re",
                "fields": {"action": "EVENT_NAME", "reengagement_action": "click", "mode": "BUDGET_CENTRIC", "rate": 1}
            },
            "OPTIMIZE_CTV_ASSIST_FOR_APP_UA": {
                "sub_key": "optimize_ctv_assist_for_app_ua",
                "fields": {"target_app_bundles": {"ANDROID": "com.example", "IOS": "id123"}}
            }
        },
        "notes": [
            "CRITICAL: The goal sub-key MUST match the goal type exactly",
            "E.g. OPTIMIZE_CPA_FOR_APP_RE requires optimize_cpa_for_app_re, NOT optimize_app_installs",
        ],
    },
}


# ═════════════════════════════════════════════════════════════════════
# Creative specifications by format type
# ═════════════════════════════════════════════════════════════════════

CREATIVE_SPECS = {
    "image": {
        "description": "Standard IMAGE creatives — exactly 9 supported sizes",
        "formats": ["JPEG", "JPG", "PNG", "GIF"],
        "max_size_kb": 500,  # 1MB for GIF
        "supported_sizes": [
            (300, 250), (320, 480), (320, 50), (728, 90),
            (480, 320), (768, 1024), (1024, 768), (300, 50), (468, 60),
        ],
        "recommended": [(300, 250), (320, 480), (320, 50), (728, 90)],
        "optional": [(480, 320), (768, 1024), (1024, 768), (300, 50), (468, 60)],
    },
    "native_image": {
        "description": "NATIVE image creatives — different sizes, require text fields + icon",
        "formats": ["JPEG", "JPG", "PNG", "GIF"],
        "max_size_kb": 500,
        "supported_sizes": [
            (1200, 628), (1200, 600), (720, 720), (720, 960), (720, 1280), (1200, 1600),
        ],
        "required_text_fields": {
            "headline": "max 70 chars (keep under 25 bytes for best display)",
            "description": "max 90 chars (emojis OK)",
            "cta_text": "max 100 chars (e.g. 'Install Now', 'Play Free')",
            "sponsored_by": "max 25 chars (advertiser name)",
        },
        "required_assets": {
            "icon": "256x256 min, 1:1 ratio, PNG recommended, max 500KB",
            "image": "one of the supported_sizes above",
        },
    },
    "video": {
        "description": "Standard VIDEO creatives — flexible sizes, endcard required",
        "format": "MP4",
        "max_size_mb": 300,
        "min_dimension": 640,
        "recommended_min": 720,
        "duration_range": (6, 120),
        "recommended_durations": [15, 30, 60],
        "min_fps": 24,
        "orientations": {
            "landscape": {"examples": [(1920, 1080), (1280, 720)]},
            "portrait": {"examples": [(1080, 1920), (720, 1280)]},
            "square": {"examples": [(720, 720)]},
        },
        "endcard": {
            "formats": ["JPEG", "JPG", "PNG", "GIF"],
            "max_size_kb": 500,
            "min_dimension": 320,
            "must_match_video_orientation": True,
        },
        "note": "Videos <30s are auto-looped to 60s. Auto-transcoded to <13MB.",
    },
    "native_video": {
        "description": "NATIVE video creatives — require text fields + icon + thumbnail",
        "format": "MP4",
        "max_size_mb": 10,
        "duration_range": (6, 100),
        "recommended_duration": 30,
        "min_fps": 24,
        "sizes": {"landscape": (1280, 720), "portrait": (720, 1280), "square": (720, 720)},
        "thumbnail_sizes": [(1280, 720), (720, 1280), (720, 720), (1200, 628), (800, 418)],
        "required_text_fields": {
            "headline": "max 70 chars",
            "description": "max 90 chars",
            "cta_text": "max 100 chars",
            "sponsored_by": "max 25 chars",
        },
        "required_assets": {"icon": "256x256 min, 1:1 ratio", "thumbnail": "must match video aspect ratio"},
    },
    "playable": {
        "description": "HTML5 playable/IEC — cannot be auto-generated",
        "format": "HTML5 (.html/.htm)",
        "max_size_mb": 5,
        "note": "Must be self-contained (all assets data-URI-compressed). Cannot generate automatically.",
    },
}


# ═════════════════════════════════════════════════════════════════════
# Metrics glossary — advertising metrics knowledge for reporting
# ═════════════════════════════════════════════════════════════════════

METRICS_GLOSSARY = {
    "metrics": {
        "CPM": {
            "name": "Cost Per Mille (Thousand Impressions)",
            "formula": "spend / impressions × 1000",
            "direction": "lower_is_better",
            "category": "upper_funnel",
            "description": "Cost to show your ad 1,000 times. Reflects auction competitiveness and inventory quality.",
            "report_fields": ["spend", "impressions"],
        },
        "CTR": {
            "name": "Click-Through Rate",
            "formula": "clicks / impressions × 100",
            "direction": "higher_is_better",
            "category": "upper_funnel",
            "description": "Percentage of impressions that result in a click. Measures creative appeal.",
            "report_fields": ["clicks", "impressions"],
        },
        "CVR": {
            "name": "Conversion Rate (Click-to-Install)",
            "formula": "installs / clicks × 100",
            "direction": "higher_is_better",
            "category": "upper_funnel",
            "description": "Percentage of clicks that result in an install. Reflects store listing quality and audience targeting.",
            "report_fields": ["installs", "clicks"],
        },
        "IPM": {
            "name": "Installs Per Mille (Thousand Impressions)",
            "formula": "installs / impressions × 1000",
            "direction": "higher_is_better",
            "category": "install",
            "description": "Installs per 1,000 impressions. Combines creative appeal (CTR) and store conversion (CVR). Declining IPM often signals creative fatigue.",
            "report_fields": ["installs", "impressions"],
        },
        "CPI": {
            "name": "Cost Per Install",
            "formula": "spend / installs",
            "direction": "lower_is_better",
            "category": "install",
            "description": "Cost to acquire one app install. The primary UA metric for install-optimized campaigns. CPI = CPM / IPM.",
            "report_fields": ["spend", "installs"],
        },
        "CPA": {
            "name": "Cost Per Action (Post-Install Event)",
            "formula": "spend / conversions",
            "direction": "lower_is_better",
            "category": "post_install",
            "description": "Cost to acquire one post-install conversion event (e.g., first deposit, purchase, registration). The primary metric for CPA-optimized campaigns.",
            "report_fields": ["spend", "conversions"],
            "aliases": ["CP FTD (Cost Per First Time Deposit)", "CP Deposit", "CP Purchase", "CP Registration", "CP Signup"],
            "note": "The specific event depends on the campaign goal action. 'CP FTD' means CPA where the event is first_time_deposit.",
        },
        "I2P": {
            "name": "Install-to-Purchase Rate",
            "formula": "purchasers / installs × 100",
            "direction": "higher_is_better",
            "category": "post_install",
            "description": "Percentage of installers who make a purchase. Measures post-install monetization quality.",
            "report_fields": ["conversions", "installs"],
        },
        "I2A": {
            "name": "Install-to-Action Rate",
            "formula": "converters / installs × 100",
            "direction": "higher_is_better",
            "category": "post_install",
            "description": "Percentage of installers who complete the target action. Generic version of I2P for any post-install event.",
            "report_fields": ["conversions", "installs"],
        },
        "CPP": {
            "name": "Cost Per Purchaser",
            "formula": "spend / purchasers",
            "direction": "lower_is_better",
            "category": "post_install",
            "description": "Cost to acquire one paying user. Useful when optimizing for monetization quality.",
            "report_fields": ["spend", "conversions"],
        },
        "ARPPU": {
            "name": "Average Revenue Per Paying User",
            "formula": "revenue / purchasers",
            "direction": "higher_is_better",
            "category": "post_install",
            "description": "Average revenue generated by each paying user. Cohorted metric (D7, D14, etc.).",
            "report_fields": ["revenue", "conversions"],
        },
        "ARPU": {
            "name": "Average Revenue Per User (All Installs)",
            "formula": "revenue / installs",
            "direction": "higher_is_better",
            "category": "post_install",
            "description": "Average revenue per install (including non-payers). ARPU = ARPPU × I2P.",
            "report_fields": ["revenue", "installs"],
        },
        "ROAS": {
            "name": "Return On Ad Spend",
            "formula": "revenue / spend × 100",
            "direction": "higher_is_better",
            "category": "revenue",
            "description": "Revenue earned per dollar spent, as a percentage. 100% = break-even. The primary metric for revenue-optimized campaigns.",
            "report_fields": ["revenue", "spend"],
            "variants": {
                "Capped ROAS": "Revenue capped at a maximum per user to reduce whale distortion",
                "Total ROAS": "Uncapped total revenue divided by spend",
                "D7 ROAS": "Revenue within 7 days of install / spend (most common default)",
            },
        },
        "Retention": {
            "name": "D{N} Retention Rate",
            "formula": "users_active_on_day_N / installs × 100",
            "direction": "higher_is_better",
            "category": "retention",
            "description": "Percentage of users who return on day N after install. Common cohorts: D1, D3, D7, D14, D28, D30.",
            "report_fields": ["installs"],
            "note": "Not directly in Moloco report API — typically from MMP (AppsFlyer, Adjust) data.",
        },
        "CPC": {
            "name": "Cost Per Click",
            "formula": "spend / clicks",
            "direction": "lower_is_better",
            "category": "other",
            "description": "Cost per ad click. Useful for click-optimized campaigns or diagnosing funnel issues.",
            "report_fields": ["spend", "clicks"],
        },
        "CPD": {
            "name": "Cost Per Download",
            "formula": "spend / downloads",
            "direction": "lower_is_better",
            "category": "other",
            "description": "Synonym for CPI in some contexts. Prefer CPI for Moloco campaigns.",
            "report_fields": ["spend", "installs"],
        },
        "Win Rate": {
            "name": "Auction Win Rate",
            "formula": "impressions / bids × 100",
            "direction": "context_dependent",
            "category": "other",
            "description": "Percentage of bid requests won. Low win rate may indicate underbidding; very high may indicate overpaying.",
            "report_fields": ["impressions"],
            "note": "Not directly in standard reports — available in log-level data.",
        },
    },
    "relationships": {
        "CPI_decomposition": "CPI = CPM / IPM = CPM / (CTR × CVR × 1000)",
        "ROAS_decomposition": "ROAS = IPM × ARPPU × I2P / CPM = (Revenue per install) / CPI",
        "CPA_from_CPI": "CPA = CPI / I2A (install-to-action rate)",
        "ARPU_decomposition": "ARPU = ARPPU × I2P",
    },
    "diagnostic_framework": {
        "description": "Top-down funnel troubleshooting when a KPI degrades",
        "steps": [
            {
                "step": 1,
                "check": "CPM",
                "question": "Is the cost of impressions rising?",
                "if_yes": "Market competition or seasonal pressure. Check auction dynamics, expand targeting, or adjust bids.",
                "if_no": "Move to step 2.",
            },
            {
                "step": 2,
                "check": "CTR / IPM",
                "question": "Is click-through or install rate declining?",
                "if_yes": "Creative fatigue or audience saturation. Refresh creatives, test new formats, expand audiences.",
                "if_no": "Move to step 3.",
            },
            {
                "step": 3,
                "check": "CVR (Click-to-Install)",
                "question": "Are clicks converting to installs at a lower rate?",
                "if_yes": "Store listing issues, targeting mismatch, or competitor activity. Review store page, check audience quality.",
                "if_no": "Move to step 4.",
            },
            {
                "step": 4,
                "check": "I2A / I2P / ROAS",
                "question": "Are post-install metrics (conversion rate, revenue) declining?",
                "if_yes": "User quality issue. Review audience targeting, check for fraud, analyze cohort behavior in MMP.",
                "if_no": "Issue may be volume-related (not enough spend to hit targets). Consider budget or bid adjustments.",
            },
        ],
    },
    "cohort_conventions": {
        "standard_windows": ["D1", "D3", "D7", "D14", "D28", "D30"],
        "default": "D7",
        "description": "Cohort windows measure post-install behavior over N days. D7 is the Moloco default for CPA/ROAS reporting. Longer windows (D14, D28) give more complete revenue pictures but delay optimization feedback.",
        "note": "When a user says 'CPA' or 'ROAS' without specifying a window, assume D7.",
    },
    "common_aliases": {
        "CP FTD": "CPA for first_time_deposit event",
        "CP Deposit": "CPA for deposit event",
        "CP Purchase": "CPA for purchase event",
        "CP Registration": "CPA for registration event",
        "CP Signup": "CPA for signup event",
        "CP Bet": "CPA for bet_placed event",
        "CPD": "Cost Per Download (synonym for CPI)",
        "eCPI": "Effective CPI (same as CPI, 'effective' used when blending sources)",
        "eCPA": "Effective CPA (same as CPA, 'effective' used when blending sources)",
    },
    "report_raw_fields": {
        "description": "Fields returned by the Moloco report API. Derived metrics must be computed from these.",
        "fields": {
            "spend": "Total ad spend in the account currency",
            "impressions": "Number of ad impressions served",
            "clicks": "Number of ad clicks",
            "installs": "Number of attributed app installs",
            "conversions": "Number of attributed post-install conversion events",
            "revenue": "Attributed revenue (cohorted, in account currency)",
            "video_views": "Number of video views (if VIDEO_PLAY_PROGRESS metric requested)",
            "engaged_views": "Number of engaged views (if ENGAGED_VIEWS metric requested)",
        },
        "derived_metrics_note": "CPI, CPA, ROAS, CPM, IPM, CTR, CVR, etc. are NOT returned directly — compute them from the raw fields above using the formulas in the metrics section.",
    },
}


# ═════════════════════════════════════════════════════════════════════
# Server instructions — usage guidelines sent to the MCP client
# ═════════════════════════════════════════════════════════════════════

SERVER_INSTRUCTIONS = """
# Moloco Ads MCP Server — Usage Guidelines

## File System Access
- **MCP tools run on the HOST macOS filesystem** — files must be at local paths like /Users/stephen.lowe/Downloads/
- Use the `list_files` tool to browse directories and discover creative assets
- NEVER ask users to "upload files to chat" — access their local filesystem directly
- Common locations: ~/Downloads/, ~/Desktop/, ~/Documents/
- Always use `os.path.expanduser()` to resolve ~ paths

## CRITICAL RULE: ALWAYS Ask Before Any Action
- **Read/gather operations are FREE** — list, get, query, download, search, analyze tools can be called silently at any time.
- **EVERY other operation REQUIRES user approval first.** This means:
  1. First, gather information silently (read tools are free).
  2. Then, present a clear plan to the user explaining what you intend to do.
  3. STOP and wait for the user to say "yes", "go ahead", "do it", etc.
  4. Only AFTER the user confirms in a SEPARATE message, execute the plan.
  5. NEVER present a plan and execute it in the same response. These must be separate turns.

  This applies to ALL of the following — no exceptions:
  - Creating anything: campaigns, creatives, creative groups, ad groups, tracking links, reports, logs
  - Updating anything: budgets, ad groups, campaigns, creatives
  - Uploading anything: creative assets, videos, images
  - Deleting anything
  - Generating files: resizing images, creating video variants, converting formats
  - Assigning creatives to campaigns
  - Pausing or activating campaigns

  Even if the user says "upload this video", you must FIRST respond with:
  "Here's what I'll do:
  1. Upload video_name.mp4 to GCS
  2. Auto-extract endcard from last frame
  3. Create VIDEO creative with companion image
  Shall I proceed?"

  And only execute after they confirm.

## Naming Conventions
- Before creating any entity (campaign, creative group, tracking link, etc.), call `get_workspace_context` to see existing naming patterns in that ad account.
- Follow the same naming conventions. For example, if existing campaigns are named "iOS - UA - CPI - Sportsbook - USA" then new campaigns should follow that pattern.
- Never invent naming patterns — always match what's already there.

## CPA Campaign Events
- Before creating a CPA campaign, call `list_product_events` to see which events are available for optimization.
- The `action` parameter in the goal MUST be one of the events defined on the product.
- Show the user the available events and let them choose.

## Creative Coverage — DEFAULT: FULL COVERAGE

**WORKFLOW FOR CREATIVE UPLOADS (follow this EXACTLY):**

Step 1: Call `plan_creative_upload` (read-only, no confirmation needed)
  - This analyzes the folder and returns: file classifications, coverage plan, estimated counts, and suggested native copy

Step 2: Present the plan to the user in your response:
  - Show the file list with dimensions and types
  - Show a table: FORMAT | COUNT | DETAILS
  - Show the suggested native copy and ask if it looks good
  - Ask for approval before executing

Step 3: Only after user approves, call `upload_creative_folder` with:
  - native_text filled in (from the approved copy)
  - generate_video_from_images: true (default)
  - All campaigns specified
  - This creates IMAGE + VIDEO + NATIVE IMAGE + NATIVE VIDEO in one pass

CRITICAL RULES:
- ALWAYS call plan_creative_upload FIRST. Never skip straight to upload_creative_folder.
- NEVER upload without native_text. The plan tool will suggest copy for you.
- NEVER upload standard sizes first and ask about native/video later. Do it ALL in one shot.
- Video resizing uses letterbox (black bars) to preserve all content.
- Playable/IEC creatives cannot be auto-generated.

COMMON MISTAKES (NEVER do these):
- WRONG: Calling plan_creative_upload and upload_creative_folder in the same turn
- WRONG: Calling upload_creative_folder without native_text when source/native images exist
- WRONG: Auto-confirming an action without the user seeing and approving the details
- WRONG: Presenting a plan and executing it in the same response

## Update Operations
- The Moloco API requires COMPLETE objects for updates, not partial updates.
- Always fetch the current object first (get_*), modify only the needed fields, then submit the full object.
- Never replace creative_group_ids on ad groups — always merge with existing IDs.

## Budget Values
- amount_micros is always a STRING, not a number. Dollars × 1,000,000. Example: $500 = "500000000"

## Reporting & Metrics
- **Top 3 KPIs**: CPI (spend/installs), CPA (spend/conversions), ROAS (revenue/spend × 100%)
- **Common aliases**: "CP FTD" = CPA for first-time deposit; "CP Purchase" = CPA for purchase event; any "CP {event}" = CPA for that event
- **Cohort default**: D7 (7 days post-install). When users say "CPA" or "ROAS" without a window, assume D7.
- **Reports return raw fields** (spend, impressions, clicks, installs, conversions, revenue). Derived metrics (CPI, ROAS, CPM, IPM, CTR, etc.) must be computed from these fields.
- **Key formulas**: CPI = spend / installs; IPM = installs / impressions × 1000; ROAS = revenue / spend; CPM = spend / impressions × 1000
- **Diagnostic framework** (when a KPI degrades, check top-down):
  1. CPM rising? → Market pressure / auction dynamics
  2. CTR/IPM declining? → Creative fatigue — refresh creatives
  3. CVR declining? → Store listing or targeting mismatch
  4. I2A/ROAS declining? → User quality issue — review audience targeting
- For full metric definitions, formulas, and relationships, read resource `moloco://specs/metrics-glossary`
"""

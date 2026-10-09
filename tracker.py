import datetime
import json
import os
import urllib.request
from apify_client import ApifyClient

DATA_FILE = "reviews_data.json"


def send_slack_alert(webhook_url, message_text):
    if not webhook_url:
        print("⚠️ SLACK_WEBHOOK_URL environment variable is missing or blank.")
        return
    payload = {"text": message_text}
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        webhook_url, data=data, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req) as response:
            print("📢 Slack alert dispatched successfully!")
    except Exception as e:
        print(f"❌ Failed to send Slack alert: {e}")


def load_previous_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"last_updated": None, "reviews": {}, "missing_counts": {}}


def save_current_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def run_tracker():
    apify_token = os.environ.get("APIFY_TOKEN")
    business_url = os.environ.get("BUSINESS_URL")
    slack_webhook = os.environ.get("SLACK_WEBHOOK_URL")

    if not apify_token or not business_url:
        raise ValueError("Missing APIFY_TOKEN or BUSINESS_URL secrets.")

    client = ApifyClient(token=apify_token)

    run_input = {
        "startUrls": [{"url": business_url}],
        "maxReviews": 1000,
        "reviewsSort": "newest",
    }

    actor_call = client.actor("compass/google-maps-reviews-scraper").call(
        run_input=run_input
    )

    try:
        dataset_id = actor_call["defaultDatasetId"]
    except (TypeError, KeyError):
        dataset_id = getattr(
            actor_call,
            "default_dataset_id",
            getattr(actor_call, "defaultDatasetId", None),
        )

    dataset_items = client.dataset(dataset_id).list_items().items

    current_reviews = {}
    for item in dataset_items:
        if isinstance(item, dict):
            r_id = (
                item.get("reviewId")
                or item.get("id")
                or item.get("reviewUrl")
            )
            author = item.get("name") or item.get("authorTitle") or "Anonymous"
            rating = (
                item.get("stars")
                or item.get("rating")
                or item.get("reviewRating")
            )
            text = (
                item.get("text")
                or item.get("reviewText")
                or item.get("comment", "")
            )
            date = item.get("publishedAtDate") or item.get("date")
        else:
            r_id = (
                getattr(item, "review_id", None)
                or getattr(item, "id", None)
                or getattr(item, "review_url", None)
            )
            author = getattr(item, "name", "Anonymous")
            rating = getattr(item, "stars", None) or getattr(item, "rating", None)
            text = getattr(item, "text", "")
            date = getattr(item, "published_at_date", None)

        if r_id:
            current_reviews[str(r_id)] = {
                "author": author,
                "rating": rating,
                "text": text,
                "date": date,
            }

    previous_snapshot = load_previous_data()
    previous_reviews = previous_snapshot.get("reviews", {})
    missing_counts = previous_snapshot.get("missing_counts", {})

    new_reviews = []
    truly_removed_reviews = []
    rating_changes = []

    # Check for missing reviews (Requires 2 consecutive misses before declaring deleted)
    updated_missing_counts = {}
    for r_id, old_data in previous_reviews.items():
        if r_id not in current_reviews:
            count = missing_counts.get(r_id, 0) + 1
            if count >= 2:
                truly_removed_reviews.append({"id": r_id, "data": old_data})
            else:
                current_reviews[r_id] = old_data
                updated_missing_counts[r_id] = count

    # Detect New Reviews or Rating Changes
    for r_id, new_data in current_reviews.items():
        if r_id not in previous_reviews and r_id not in updated_missing_counts:
            new_reviews.append({"id": r_id, "data": new_data})
        elif r_id in previous_reviews:
            old_rating = previous_reviews[r_id].get("rating")
            if old_rating and old_rating != new_data["rating"]:
                rating_changes.append(
                    {
                        "id": r_id,
                        "old_rating": old_rating,
                        "new_rating": new_data["rating"],
                        "author": new_data["author"],
                    }
                )

    total_reviews = len(current_reviews)
    ratings = [
        r["rating"] for r in current_reviews.values() if r.get("rating")
    ]
    avg_rating = sum(ratings) / len(ratings) if ratings else 0

    today = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%d %H:%M UTC"
    )

    print("\n" + "=" * 45)
    print(f" DAILY GOOGLE REVIEWS REPORT — {today}")
    print("=" * 45)
    print(f"Total Active Reviews : {total_reviews}")
    print(f"Average Rating       : {avg_rating:.2f} ⭐")
    print(f"New Reviews Today    : {len(new_reviews)}")
    print(f"Confirmed Removed    : {len(truly_removed_reviews)}")
    print(f"Rating Changes Today : {len(rating_changes)}")
    print("-" * 45 +

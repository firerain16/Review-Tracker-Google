import datetime
import json
import os
from apify_client import ApifyClient

DATA_FILE = "reviews_data.json"


def load_previous_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"last_updated": None, "reviews": {}}


def save_current_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def run_tracker():
    apify_token = os.environ.get("APIFY_TOKEN")
    business_url = os.environ.get("BUSINESS_URL")

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

    # Safely extract dataset ID whether Apify returns a dict or an object
    if isinstance(actor_call, dict):
        dataset_id = actor_call.get("defaultDatasetId") or actor_call.get("default_dataset_id")
    else:
        dataset_id = getattr(actor_call, "default_dataset_id", None) or getattr(actor_call, "defaultDatasetId", None)

    # Fetch extracted items from Apify dataset
    dataset_items = client.dataset(dataset_id).list_items().items

    current_reviews = {}
    for item in dataset_items:
        if isinstance(item, dict):
            r_id = (
                item.get("reviewId")
                or item.get("id")
                or item.get("reviewUrl")
                or item.get("name")
            )
            author = item.get("name") or item.get("authorTitle") or "Anonymous"
            rating = item.get("stars") or item.get("rating") or item.get("reviewRating")
            text = item.get("text") or item.get("reviewText") or item.get("comment", "")
            date = item.get("publishedAtDate") or item.get("date")
        else:
            r_id = getattr(item, "review_id", None) or getattr(item, "id", None) or getattr(item, "name", None)
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

    new_reviews = []
    removed_reviews = []
    rating_changes = []

    for r_id, old_data in previous_reviews.items():
        if r_id not in current_reviews:
            removed_reviews.append({"id": r_id, "data": old_data})

    for r_id, new_data in current_reviews.items():
        if r_id not in previous_reviews:
            new_reviews.append({"id": r_id, "data": new_data})
        else:
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
    print(f"Removed Reviews Today: {len(removed_reviews)}")
    print(f"Rating Changes Today : {len(rating_changes)}")
    print("-" * 45)

    if removed_reviews:
        print("\n🚨 REMOVED REVIEWS DETECTED:")
        for r in removed_reviews:
            print(
                f" - [{r['data'].get('rating')}⭐] {r['data'].get('author')}: \"{r['data'].get('text')}\""
            )

    if new_reviews:
        print("\n✨ NEW REVIEWS ADDED:")
        for r in new_reviews:
            print(
                f" - [{r['data'].get('rating')}⭐] {r['data'].get('author')}: \"{r['data'].get('text')}\""
            )

    if rating_changes:
        print("\n⚠️ RATING CHANGES DETECTED:")
        for r in rating_changes:
            print(
                f" - {r['author']}: Changed from {r['old_rating']}⭐ to {r['new_rating']}⭐"
            )

    print("=" * 45 + "\n")

    updated_snapshot = {
        "last_updated": today,
        "total_reviews": total_reviews,
        "average_rating": round(avg_rating, 2),
        "reviews": current_reviews,
    }
    save_current_data(updated_snapshot)


if __name__ == "__main__":
    run_tracker()

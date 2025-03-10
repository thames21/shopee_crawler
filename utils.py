import requests
import pandas as pd
import os, time, random, re, csv
from urllib.parse import urlparse
import json


def load_urls(url_file):
    try:
        df = pd.read_csv(url_file)
        df["ratings_to_scrape"] = df["ratings_to_scrape"].apply(json.loads)
        return df
    except FileNotFoundError:
        return pd.DataFrame(columns=["name", "url", "status", "ratings_to_scrape"])


def update_ratings_to_scrape(url, failed_ratings, url_file):
    df = load_urls(url_file)
    df.loc[df["url"] == url, "ratings_to_scrape"] = json.dumps(failed_ratings)
    df.to_csv(url_file, index=False)


def update_url_status(url, status, url_file):
    df = load_urls(url_file)
    df.loc[df["url"] == url, "status"] = status
    df.to_csv(url_file, index=False)


def reset_url_status(url_file):
    df = load_urls(url_file)
    df["status"] = "not scraped"
    df["ratings_to_scrape"] = [json.dumps([1, 2, 3, 4, 5])] * len(df)
    df.to_csv(url_file, index=False)
    try:
        os.remove('reviews.csv')
    except FileNotFoundError:
        print("reviews.csv not found, cannot delete.")


def extract_shopee_ids(url):
    try:
        parsed_url = urlparse(url)
        path = parsed_url.path
        match = re.search(r"i\.(\d+)\.(\d+)", path)
        if match:
            item_id = int(match.group(1))
            shop_id = int(match.group(2))
            return item_id, shop_id
    except Exception as e:
        print(f"Error parsing URL: {e}")
        return None
    

def preprocess_comment(comment):
    # Remove multiple spaces
    comment = re.sub(r"\s+", " ", comment).strip()
    # Remove quotation marks
    comment = comment.replace('"', "")
    return comment.lower()


def initialize_csv(file_path, columns):
    if not os.path.exists(file_path) or os.stat(file_path).st_size == 0:
        pd.DataFrame(columns=columns).to_csv(file_path, index=False, encoding="utf-8")


USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_3 like Mac OS X) AppleWebKit/537.36 (KHTML, like Gecko) Version/16.3 Mobile/15E148 Safari/537.36",
    "Mozilla/5.0 (Linux; Android 11; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36",
]


def get_shopee_reviews(shop_id, item_id, ratings_to_scrape):
    reviews_list = []
    limit = 15  # Shopee allows a max of 50 per request
    target_count = 15

    # Initialise a dictionary to count the number of reviews collected for each rating type
    collected_reviews = dict.fromkeys(ratings_to_scrape, 0)
    failed_ratings = []     # List to keep track 403 ratings

    for rating in ratings_to_scrape:
        offset = 0  # Reset offset

        while collected_reviews[rating] < target_count:
            headers = {
                "User-Agent": random.choice(USER_AGENTS),
                "Referer": f"https://shopee.vn/product/{shop_id}/{item_id}",
                "Accept-Language": "en-US,en;q=0.9",
                "X-Requested-With": "XMLHttpRequest"
            }

            # Shopee API
            url = f"https://shopee.vn/api/v2/item/get_ratings?itemid={item_id}&shopid={shop_id}&limit={limit}&offset={offset}&type={rating}&filter=1"
            
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code != 200:
                print(f"Failed rating {rating}, status:", response.status_code)
                failed_ratings.append(rating)
                break
                
            data = response.json().get("data", {}).get("ratings", [])
            if not data:
                break
            for r in data:
                if collected_reviews[rating] >= target_count:
                    break 
                comment = r.get("comment", "")
                if comment:
                    reviews_list.append({
                        "comment": preprocess_comment(comment),
                        "label": None
                    })
                    collected_reviews[rating] += 1

            offset += limit  # Move to the next batch
            time.sleep(random.uniform(2, 5))

    if reviews_list:
        pd.DataFrame(reviews_list).to_csv('reviews.csv', mode='a', header=False, index=False, encoding='utf-8', quoting=csv.QUOTE_ALL)
 
    return failed_ratings


def scrape_reviews(url_file):
    df = load_urls(url_file)
    df_unprocessed = df[df["status"] != "scraped"]
    if df_unprocessed.empty:
        print("No URLs left to scrape.")
        return True

    initialize_csv('reviews.csv', ["comment", "label"])

    for _, row in df_unprocessed.iterrows():
        name, url, ratings_to_scrape = row["name"], row["url"], row["ratings_to_scrape"]
        if isinstance(ratings_to_scrape, str):  
            ratings_to_scrape = json.loads(ratings_to_scrape)
        print(f"Scraping {name}, ratings to scrape: {ratings_to_scrape}")

        try:
            shop_id, item_id = extract_shopee_ids(url)
            failed_ratings = get_shopee_reviews(shop_id, item_id, ratings_to_scrape)
            update_ratings_to_scrape(url, failed_ratings, url_file)
            if not failed_ratings:
                update_url_status(url, "scraped", url_file)
        except Exception as e:
            print(f"Error scraping {url}: {e}")
            update_url_status(url, "failed", url_file)

        time.sleep(2)

    print("One epoch completed.")
    return False #urls remain to be scraped

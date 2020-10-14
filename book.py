import requests
res = requests.get("https://www.goodreads.com/book/review_counts.json", params={"key": "3CMk3TXO1bhGL2LZj5qg", "isbns": "9781632168146"})
print(res.json())
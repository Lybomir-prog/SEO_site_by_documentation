import feedparser
def parser_rss(url:str):
    feed=feedparser.parse(url)
    items=[]
    for entry in feed.entries:
        items.append({
            "title": getattr(entry, "title" , ""),
            "link": getattr(entry, "link" , ""),
            "published": getattr(entry, "published" , ""),
            "summary": getattr(entry, "summary" , "")
        })
    return items
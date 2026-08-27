import asyncio
import pandas as pd
from playwright.async_api import async_playwright

async def find_detective_agencies(location: str = "Delhi NCR", keyword: str = "Detective Agency"):
    print(f"🔍 Searching Google Maps for '{keyword}' in '{location}'...")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        
        search_query = f"{keyword} in {location}"
        url = f"https://www.google.com/maps/search/{search_query.replace(' ', '+')}"
        
        await page.goto(url)
        await page.wait_for_timeout(5000)

        # Scroll down to load multiple agency listings
        for _ in range(4):
            await page.mouse.wheel(0, 3000)
            await page.wait_for_timeout(2000)

        listings = await page.locator('a[href*="/maps/place/"]').all()
        leads = []
        seen_names = set()

        for listing in listings:
            try:
                name = await listing.get_attribute("aria-label")
                if name and name not in seen_names:
                    seen_names.add(name)
                    
                    # Generate candidate contact email format for local agencies
                    sanitized_name = "".join(e for e in name.lower() if e.isalnum())
                    placeholder_email = f"info@{sanitized_name}.com"
                    
                    leads.append({
                        "Agency_Name": name,
                        "Target_Location": location,
                        "Contact_Email": placeholder_email,
                        "Status": "Prospect Lead"
                    })
            except Exception:
                continue

        await browser.close()
        
        df = pd.DataFrame(leads)
        output_file = "agency_leads.csv"
        df.to_csv(output_file, index=False)
        print(f"✅ Successfully extracted {len(leads)} leads into '{output_file}'!")

if __name__ == "__main__":
    asyncio.run(find_detective_agencies())  
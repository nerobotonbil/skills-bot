#!/usr/bin/env python3
"""
Initialize streak with 3-day history by creating snapshots
Run this script on Railway to initialize the streak system
"""
import json
import os
import sys
from datetime import date, timedelta
import httpx
import asyncio

# Add parent directory to path to import config
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.settings import NOTION_SKILLS_DATABASE_ID

PRODUCTIVITY_FILE = "/tmp/productivity_data.json"

async def get_current_skills():
    """Get current skill values from Notion"""
    token = os.getenv("NOTION_API_TOKEN")
    if not token:
        print("ERROR: NOTION_API_TOKEN not found in environment!")
        return {}
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"https://api.notion.com/v1/databases/{NOTION_SKILLS_DATABASE_ID}/query",
            headers=headers,
            json={},
            timeout=30.0
        )
        
        if response.status_code != 200:
            print(f"Error querying Notion: {response.status_code}")
            print(response.text)
            return {}
        
        data = response.json()
        pages = data.get("results", [])
        
        skills = {}
        for page in pages:
            props = page.get("properties", {})
            
            # Get skill name
            skill_name_prop = props.get("Skill", {})
            skill_name = None
            if skill_name_prop.get("type") == "title":
                title_list = skill_name_prop.get("title", [])
                if title_list:
                    skill_name = title_list[0].get("plain_text", "Unknown")
            
            if not skill_name:
                continue
            
            # Get current values
            current_values = {}
            for content_type in ["Lectures", "Practice hours", "Videos", "Films ", "VC Lectures"]:
                if content_type in props:
                    value = props[content_type].get("number", 0) or 0
                    current_values[content_type] = value
            
            skills[skill_name] = current_values
        
        return skills

async def main():
    print("=" * 60)
    print("INITIALIZING STREAK SYSTEM WITH 3-DAY HISTORY")
    print("=" * 60)
    
    print("\n1. Fetching current skills from Notion...")
    current_skills = await get_current_skills()
    
    if not current_skills:
        print("❌ No skills found! Check NOTION_API_TOKEN and database ID.")
        return
    
    print(f"✅ Found {len(current_skills)} skills")
    
    # Show some example skills
    print("\nExample skills:")
    for i, (skill_name, values) in enumerate(list(current_skills.items())[:3]):
        print(f"  - {skill_name}: {values}")
    
    # Load or create productivity data
    print("\n2. Loading productivity data...")
    if os.path.exists(PRODUCTIVITY_FILE):
        with open(PRODUCTIVITY_FILE, 'r') as f:
            data = json.load(f)
        print(f"✅ Loaded existing data from {PRODUCTIVITY_FILE}")
    else:
        data = {
            "streak": {
                "current": 0,
                "longest": 0,
                "last_practice_date": None,
                "freezes_available": 2,
                "freezes_used_this_week": 0,
                "freeze_reset_date": None
            },
            "practice_history": [],
            "milestones_achieved": [],
            "last_interleaved_skills": [],
            "deep_practice_sessions": []
        }
        print(f"✅ Created new productivity data structure")
    
    # Create snapshots for last 3 days
    print("\n3. Creating snapshots for last 3 days...")
    
    if "daily_snapshots" not in data:
        data["daily_snapshots"] = {}
    
    today = date.today()
    
    # For each of the last 3 days, create a snapshot with slightly lower values
    # to simulate progress over the days
    for days_ago in [3, 2, 1]:
        snapshot_date = (today - timedelta(days=days_ago)).isoformat()
        
        # Create snapshot with values slightly lower than current
        # Subtract days_ago from each value to simulate daily progress
        snapshot = {}
        for skill_name, values in current_skills.items():
            snapshot_values = {}
            for content_type, current_val in values.items():
                # Reduce by days_ago to simulate progress
                # This ensures today's values will be higher than yesterday's
                snapshot_val = max(0, current_val - days_ago)
                snapshot_values[content_type] = snapshot_val
            snapshot[skill_name] = snapshot_values
        
        data["daily_snapshots"][snapshot_date] = snapshot
        print(f"  ✅ Created snapshot for {snapshot_date}")
    
    # Set streak to 3 days
    print("\n4. Setting streak to 3 days...")
    data["streak"]["current"] = 3
    data["streak"]["longest"] = max(data["streak"].get("longest", 0), 3)
    data["streak"]["last_practice_date"] = (today - timedelta(days=1)).isoformat()
    print(f"  ✅ Current streak: {data['streak']['current']} days")
    print(f"  ✅ Longest streak: {data['streak']['longest']} days")
    print(f"  ✅ Last practice: {data['streak']['last_practice_date']}")
    
    # Add practice history for last 3 days
    print("\n5. Adding practice history...")
    for days_ago in [3, 2, 1]:
        practice_date = (today - timedelta(days=days_ago)).isoformat()
        data["practice_history"].append({
            "date": practice_date,
            "skills_practiced": ["Memory Enhancement", "Research Skills"],
            "duration_mins": 60
        })
        print(f"  ✅ Added practice entry for {practice_date}")
    
    # Save data
    print("\n6. Saving data...")
    with open(PRODUCTIVITY_FILE, 'w') as f:
        json.dump(data, f, indent=2)
    print(f"  ✅ Saved to {PRODUCTIVITY_FILE}")
    
    print("\n" + "=" * 60)
    print("✅ STREAK INITIALIZATION COMPLETE!")
    print("=" * 60)
    print(f"\nSummary:")
    print(f"  • Current streak: {data['streak']['current']} days")
    print(f"  • Longest streak: {data['streak']['longest']} days")
    print(f"  • Last practice: {data['streak']['last_practice_date']}")
    print(f"  • Snapshots created: {len(data['daily_snapshots'])} days")
    print(f"  • Practice history entries: {len(data['practice_history'])}")
    
    print("\nSnapshot dates:")
    for snapshot_date in sorted(data["daily_snapshots"].keys()):
        print(f"  • {snapshot_date}")
    
    print("\n✅ The bot will now correctly detect today's progress!")
    print("   Try checking your streak with /streak command")

if __name__ == "__main__":
    asyncio.run(main())

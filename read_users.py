import asyncio
import json

# This function reads the JSON file
async def read_users(filename):
    print(f"📂 Reading file: {filename}\n")
    
    # Open and load the JSON file
    with open(filename, "r") as file:
        data = json.load(file)
    
    return data["users"]

# This function prints one user nicely
async def print_user(user):
    print("👤 User Info:")
    print(f"   Name    : {user['name']}")
    print(f"   Email   : {user['email']}")
    print(f"   Phone   : {user['phone']}")
    print(f"   Address : {user['address']}")
    print("-" * 40)

# Main function - this is where everything runs
async def main():
    print("🚀 Starting User Memory System\n")
    
    # Read all users from JSON
    users = await read_users("users.json")
    
    # Print each user one by one
    for user in users:
        await print_user(user)
    
    print(f"\n✅ Total users loaded: {len(users)}")

# This runs the async main function
if __name__ == "__main__":
    asyncio.run(main())
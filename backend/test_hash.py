"""
A toy script to test pw hashing, using the same
encryption I use in the API

bcrypt creates always 60 character hashes, with 
random salt added so that same passwords give different outputs
"""

from passlib.context import CryptContext

# Configure bcrypt hashing

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    """Hash a plain text password"""
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain text password against a hash"""
    return pwd_context.verify(plain_password, hashed_password)

# Test the functions
if __name__ == "__main__":
    print("=" * 50)
    print("PASSWORD HASHING TEST")
    print("=" * 50)

    plain_password = "mysecret123"
    hashed = hash_password(plain_password)
    print(f"   Plain text: {plain_password}")
    print(f"   Hashed:     {hashed}")
    print(f"   Hash length: {len(hashed)} characters")
    
    # Test 2: Verify correct password
    print("\nVerifying correct password:")
    result = verify_password(plain_password, hashed)
    print(f"   Plain text: {plain_password}")
    print(f"   Hashed:     {hashed}")
    print(f"   Match:      {result}")
    
   
    
    # Test 4: Hash the same password twice
    print("\nTesting random salt:")
    hash1 = hash_password("test123")
    hash2 = hash_password("test123")
    print(f"   Hash 1: {hash1}")
    print(f"   Hash 2: {hash2}")
    print(f"   Same?    {hash1 == hash2}")
    print("The salt is the 22 characters after the third $ !!!")
    
    # Test 5: Verify both hashes work
    print("\n5. Both hashes verify correctly:")
    print(f"   Hash 1 verifies: {verify_password('test123', hash1)}")
    print(f"   Hash 2 verifies: {verify_password('test123', hash2)}")
    
    print("\n" + "=" * 50)

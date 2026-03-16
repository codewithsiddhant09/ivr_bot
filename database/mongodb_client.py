"""
MongoDB client for contact request management.
Handles connection to MongoDB Atlas and CRUD operations for contact requests.
"""
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from pymongo import MongoClient, DESCENDING
from pymongo.errors import ConnectionFailure, PyMongoError

logger = logging.getLogger(__name__)


class MongoDBClient:
    """MongoDB client for managing contact requests."""
    
    def __init__(self, mongodb_uri: str, database_name: str = "voicechatbot"):
        """
        Initialize MongoDB client.
        
        Args:
            mongodb_uri: MongoDB connection URI
            database_name: Database name
        """
        try:
            self.client = MongoClient(mongodb_uri, serverSelectionTimeoutMS=5000)
            # Test connection
            self.client.admin.command('ping')
            self.db = self.client[database_name]
            logger.info(f"Connected to MongoDB database: {database_name}")
        except ConnectionFailure as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            raise
        except Exception as e:
            logger.error(f"Error initializing MongoDB client: {e}")
            raise
    
    def create_contact_request(
        self, 
        session_id: str,
        name: str,
        email: str,
        mobile: str,
        preferred_datetime: str,
        timezone: str,
        original_query: str,
        country: str = "Not specified"
    ) -> Optional[str]:
        """
        Create a new contact request.
        
        Args:
            session_id: Session ID
            name: User's name
            email: User's email
            mobile: User's mobile with country code
            preferred_datetime: Preferred contact date/time (flexible format)
            timezone: User's timezone (e.g., IST, UTC+5:30, EST)
            original_query: The original query that triggered the request
            country: User's country/location
            
        Returns:
            Inserted document ID as string, or None if failed
        """
        try:
            # Use a single collection for all contact requests
            collection = self.db["contact_requests"]
            
            contact_request = {
                "session_id": session_id,
                "name": name,
                "email": email,
                "mobile": mobile,
                "preferred_datetime": preferred_datetime,
                "timezone": timezone,
                "country": country,
                "original_query": original_query,
                "created_at": datetime.utcnow(),
                "status": "pending"
            }
            
            logger.info(f"Attempting to insert contact request to collection: contact_requests")
            logger.info(f"Document data: {contact_request}")
            
            result = collection.insert_one(contact_request)
            
            logger.info(f"✅ Successfully created contact request for session {session_id}")
            logger.info(f"   Collection: {collection.name}")
            logger.info(f"   Document ID: {result.inserted_id}")
            logger.info(f"   Database: {self.db.name}")
            
            # Verify the write by reading it back
            verify = collection.find_one({"_id": result.inserted_id})
            if verify:
                logger.info(f"✅ Verified: Document exists in MongoDB")
            else:
                logger.error(f"❌ Warning: Document not found after insert!")
            
            return str(result.inserted_id)
            
        except PyMongoError as e:
            logger.error(f"❌ MongoDB Error creating contact request: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ Unexpected error creating contact request: {e}")
            return None
    
    def get_contact_requests(self, session_id: str) -> List[Dict[str, Any]]:
        """
        Get all contact requests for a session.
        
        Args:
            session_id: Session ID
            
        Returns:
            List of contact requests
        """
        try:
            collection = self.db["contact_requests"]
            
            # Filter by session_id
            requests = list(collection.find({"session_id": session_id}).sort("created_at", DESCENDING))

            
            # Convert ObjectId to string for JSON serialization
            for request in requests:
                request['_id'] = str(request['_id'])
                
            return requests
            
        except PyMongoError as e:
            logger.error(f"Error retrieving contact requests: {e}")
            return []
    
    def update_contact_request_status(
        self, 
        session_id: str, 
        request_id: str, 
        status: str
    ) -> bool:
        """
        Update the status of a contact request.
        
        Args:
            session_id: Session ID
            request_id: Contact request ID
            status: New status (pending, contacted, resolved)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            from bson import ObjectId
            
            collection = self.db["contact_requests"]
            
            result = collection.update_one(
                {"_id": ObjectId(request_id)},
                {"$set": {"status": status, "updated_at": datetime.utcnow()}}
            )
            
            if result.modified_count > 0:
                logger.info(f"Updated contact request {request_id} status to {status}")
                return True
            else:
                logger.warning(f"No contact request found with ID {request_id}")
                return False
                
        except PyMongoError as e:
            logger.error(f"Error updating contact request status: {e}")
            return False
    
    def get_all_pending_requests(self) -> List[Dict[str, Any]]:
        """
        Get all pending contact requests across all sessions.
        
        Returns:
            List of pending contact requests
        """
        try:
            collection = self.db["contact_requests"]
            
            # Get all pending requests from the single collection
            requests = list(collection.find({"status": "pending"}).sort("created_at", DESCENDING))
            
            # Convert ObjectId to string
            for request in requests:
                request['_id'] = str(request['_id'])
            
            return requests

            
        except PyMongoError as e:
            logger.error(f"Error retrieving pending requests: {e}")
            return []
    
    def save_session_conversation(
        self,
        session_id: str,
        conversation_history: List[Dict[str, Any]],
        user_details: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """
        Save entire session conversation to MongoDB.
        
        Args:
            session_id: Session ID
            conversation_history: List of message dictionaries with role and content
            user_details: Optional user details (name, email, phone)
            
        Returns:
            Inserted document ID as string, or None if failed
        """
        try:
            collection = self.db["sessions"]
            
            session_doc = {
                "session_id": session_id,
                "conversation_history": conversation_history,
                "user_details": user_details or {},
                "created_at": datetime.utcnow(),
                "message_count": len(conversation_history)
            }
            
            logger.info(f"Saving session conversation for {session_id}")
            logger.info(f"Database: {self.db.name}, Collection: sessions")
            logger.info(f"Conversation has {len(conversation_history)} messages")
            
            result = collection.insert_one(session_doc)
            
            logger.info(f"✅ Successfully saved session conversation: {result.inserted_id}")
            
            # Verify the write by reading it back
            verify = collection.find_one({"_id": result.inserted_id})
            if verify:
                logger.info(f"✅ Verified: Document exists in MongoDB (session_id: {verify.get('session_id')})")
                logger.info(f"   Database: {self.db.name}, Collection: {collection.name}")
            else:
                logger.error(f"❌ Warning: Document not found after insert!")
            
            return str(result.inserted_id)
            
        except PyMongoError as e:
            logger.error(f"❌ Error saving session conversation: {e}")
            return None
    
    def list_collections(self) -> List[str]:
        """
        List all collections in the database.
        
        Returns:
            List of collection names
        """
        try:
            collections = self.db.list_collection_names()
            logger.info(f"Collections in database '{self.db.name}': {collections}")
            return collections
        except PyMongoError as e:
            logger.error(f"Error listing collections: {e}")
            return []
    
    def get_session_count(self) -> int:
        """
        Get total count of sessions saved.
        
        Returns:
            Number of session documents
        """
        try:
            collection = self.db["sessions"]
            count = collection.count_documents({})
            logger.info(f"Total sessions in database: {count}")
            return count
        except PyMongoError as e:
            logger.error(f"Error counting sessions: {e}")
            return 0
    
    def close(self):
        """Close MongoDB connection."""
        if self.client:
            self.client.close()
            logger.info("MongoDB connection closed")
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


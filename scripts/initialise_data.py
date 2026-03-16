"""
Data initialization script for the AI Agentic RAG system.
Loads and embeds documents from multiple formats (PDF, Word, TXT, MD) into ChromaDB.
"""

import logging
import os
import sys
from pathlib import Path
from typing import List, Dict, Any

# ---------------------------------------------------------------------------
# Path setup – ensure imports resolve regardless of cwd
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).resolve().parent          # .../scripts/
_PROJECT_ROOT = _SCRIPT_DIR.parent                     # .../voice-agent-be/
_SRC_DIR = _PROJECT_ROOT / "src"                       # .../voice-agent-be/src/

for p in [str(_PROJECT_ROOT), str(_SRC_DIR), str(_SCRIPT_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from vectorstore.chromadb_client import ChromaDBClient
from config import get_config
from document_loader import document_loader

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def load_privacy_policy_data(data_file_path: str) -> str:
    """
    Load document data from any supported format (PDF, Word, TXT, MD).
    
    Args:
        data_file_path: Path to the document file
        
    Returns:
        Document content as string
    """
    try:
        # Use document loader to handle multiple formats
        content = document_loader.load_document(data_file_path)
        
        logger.info(f"Loaded document from {data_file_path}")
        logger.info(f"Content length: {len(content)} characters")
        
        return content
        
    except FileNotFoundError:
        logger.error(f"Document file not found: {data_file_path}")
        raise
    except ValueError as e:
        logger.error(f"Unsupported file format: {e}")
        raise
    except Exception as e:
        logger.error(f"Error loading document: {e}")
        raise

def create_document_metadata(source_file: str) -> Dict[str, Any]:
    """
    Create metadata for the privacy policy document.
    
    Args:
        source_file: Path to the source file
        
    Returns:
        Metadata dictionary
    """
    return {
        "source": source_file,
        "document_type": "privacy_policy",
        "company": "TechGropse",
        "version": "1.0",
        "language": "english",
        "last_updated": "2024-01-01",  # Update with actual date if available
        "domain": "privacy_and_data_protection"
    }

def process_and_embed_documents(chromadb_client: ChromaDBClient, content: str, metadata: Dict[str, Any]) -> bool:
    """
    Process the privacy policy content and embed it into ChromaDB.
    
    Args:
        chromadb_client: ChromaDB client instance
        content: Privacy policy content
        metadata: Document metadata
        
    Returns:
        True if successful, False otherwise
    """
    try:
        logger.info("Processing privacy policy content into chunks...")
        
        # Load and chunk the document
        documents = chromadb_client.load_and_chunk_document_from_text(
            text=content,
            metadata=metadata
        )
        
        if not documents:
            logger.error("No documents were created from the content")
            return False
        
        logger.info(f"Created {len(documents)} document chunks")
        
        # Add documents to ChromaDB
        logger.info("Embedding documents into ChromaDB...")
        success = chromadb_client.add_documents(documents)
        
        if success:
            logger.info(f"Successfully embedded {len(documents)} documents into ChromaDB")
            
            # Log some sample chunks for verification
            logger.info("Sample document chunks:")
            for i, doc in enumerate(documents[:3]):
                chunk_preview = doc.page_content[:100].replace('\n', ' ')
                logger.info(f"  Chunk {i+1}: {chunk_preview}...")
            
            return True
        else:
            logger.error("Failed to embed documents into ChromaDB")
            return False
            
    except Exception as e:
        logger.error(f"Error processing and embedding documents: {e}")
        return False

def verify_embeddings(chromadb_client: ChromaDBClient) -> bool:
    """
    Verify that the embeddings were created successfully by performing test searches.
    
    Args:
        chromadb_client: ChromaDB client instance
        
    Returns:
        True if verification successful, False otherwise
    """
    try:
        logger.info("Verifying embeddings with test searches...")
        
        # Test queries
        test_queries = [
            "privacy policy",
            "personal data collection",
            "contact information",
            "cookies",
            "data security"
        ]
        
        all_tests_passed = True
        
        for query in test_queries:
            try:
                results = chromadb_client.similarity_search(query, k=3)
                
                if results:
                    logger.info(f"✓ Query '{query}': Found {len(results)} relevant documents")
                    
                    # Log the first result for verification
                    if len(results) > 0:
                        preview = results[0].page_content[:100].replace('\n', ' ')
                        logger.info(f"  Top result: {preview}...")
                else:
                    logger.warning(f"✗ Query '{query}': No results found")
                    all_tests_passed = False
                    
            except Exception as e:
                logger.error(f"✗ Query '{query}' failed: {e}")
                all_tests_passed = False
        
        if all_tests_passed:
            logger.info("✓ All verification tests passed")
        else:
            logger.warning("Some verification tests failed")
        
        return all_tests_passed
        
    except Exception as e:
        logger.error(f"Error during verification: {e}")
        return False

def add_documents_incremental(data_file_paths: List[str], category: str = "policy") -> bool:
    """
    Add new documents to existing ChromaDB collection WITHOUT resetting.
    
    Args:
        data_file_paths: List of paths to data files to add
        category: Category for the documents (e.g., "privacy", "terms", "cookies")
        
    Returns:
        True if successful, False otherwise
    """
    try:
        logger.info("Adding documents incrementally to existing collection...")
        
        # Initialize ChromaDB client
        chromadb_client = ChromaDBClient()
        
        # Get current collection info
        collection_info = chromadb_client.get_collection_info()
        initial_count = collection_info.get("count", 0)
        logger.info(f"Current collection contains {initial_count} documents")
        
        total_added = 0
        
        for data_file_path in data_file_paths:
            # Ensure data file exists
            if not os.path.exists(data_file_path):
                logger.error(f"Data file not found: {data_file_path}")
                continue
            
            logger.info(f"Processing file: {data_file_path}")
            
            # Load document data
            content = load_privacy_policy_data(data_file_path)
            
            # Create enhanced metadata with category
            from datetime import datetime
            metadata = {
                "source": data_file_path,
                "document_type": "policy",
                "category": category,
                "company": "TechGropse",
                "version": "1.0",
                "language": "english",
                "last_updated": datetime.now().isoformat(),
                "domain": "privacy_and_data_protection"
            }
            
            # Process and embed documents (adds to existing collection)
            success = process_and_embed_documents(chromadb_client, content, metadata)
            
            if success:
                # Count how many chunks were added
                chunks = chromadb_client.load_and_chunk_document_from_text(content, metadata)
                total_added += len(chunks)
                logger.info(f"✓ Added {len(chunks)} chunks from {data_file_path}")
            else:
                logger.error(f"✗ Failed to add documents from {data_file_path}")
        
        # Get final collection info
        final_info = chromadb_client.get_collection_info()
        final_count = final_info.get("count", 0)
        
        logger.info(f"Collection updated: {initial_count} → {final_count} documents")
        logger.info(f"✓ Successfully added {total_added} new document chunks")
        
        return True
        
    except Exception as e:
        logger.error(f"Error adding documents incrementally: {e}")
        return False


def initialize_chromadb_data(data_file_path: str = None, reset_collection: bool = False) -> bool:
    """
    Main function to initialize ChromaDB with privacy policy data.
    
    Args:
        data_file_path: Optional path to data file (defaults to ./data/info.txt)
        reset_collection: Whether to reset the existing collection
        
    Returns:
        True if initialization successful, False otherwise
    """
    try:
        # Set default data file path
        if not data_file_path:
            data_file_path = "data/info.txt"
        
        # Ensure data file exists
        if not os.path.exists(data_file_path):
            logger.error(f"Data file not found: {data_file_path}")
            return False
        
        logger.info("Initializing ChromaDB with privacy policy data...")
        logger.info(f"Data source: {data_file_path}")
        
        # Load configuration
        config = get_config()
        
        # Initialize ChromaDB client
        logger.info("Initializing ChromaDB client...")
        chromadb_client = ChromaDBClient()
        
        # Reset collection if requested
        if reset_collection:
            logger.info("Resetting ChromaDB collection...")
            chromadb_client.reset_collection()
        
        # Check if collection already has data
        collection_info = chromadb_client.get_collection_info()
        document_count = collection_info.get("count", 0)
        
        if document_count > 0 and not reset_collection:
            logger.info(f"Collection already contains {document_count} documents")
            response = input("Do you want to reset and reload the data? [y/N]: ")
            if response.lower().startswith('y'):
                logger.info("Resetting collection...")
                chromadb_client.reset_collection()
            else:
                logger.info("Keeping existing data. Running verification only...")
                return verify_embeddings(chromadb_client)
        
        # Load privacy policy data
        logger.info("Loading privacy policy data...")
        content = load_privacy_policy_data(data_file_path)
        
        # Create enhanced metadata
        from datetime import datetime
        metadata = {
            "source": data_file_path,
            "document_type": "policy",
            "category": "privacy",  # Default category
            "company": "TechGropse",
            "version": "1.0",
            "language": "english",
            "last_updated": datetime.now().isoformat(),
            "domain": "privacy_and_data_protection"
        }
        
        # Process and embed documents
        success = process_and_embed_documents(chromadb_client, content, metadata)
        
        if not success:
            logger.error("Failed to process and embed documents")
            return False
        
        # Verify embeddings
        verification_success = verify_embeddings(chromadb_client)
        
        # Get final collection info
        final_info = chromadb_client.get_collection_info()
        logger.info(f"Final collection info: {final_info}")
        
        if success and verification_success:
            logger.info("✓ ChromaDB initialization completed successfully!")
            logger.info(f"✓ Collection '{chromadb_client.collection_name}' now contains {final_info.get('count', 0)} documents")
            return True
        else:
            logger.error("ChromaDB initialization encountered issues")
            return False
            
    except Exception as e:
        logger.error(f"Error initializing ChromaDB data: {e}")
        return False

def main():
    """
    Main execution function.
    """
    import argparse
    
    parser = argparse.ArgumentParser(description="Initialize or update ChromaDB with document data")
    parser.add_argument("--data-file", default="data/info.txt", help="Path to data file (for init mode)")
    parser.add_argument("--reset", action="store_true", help="Reset existing collection (full reingest)")
    parser.add_argument("--incremental", nargs="+", help="Add new files incrementally without resetting")
    parser.add_argument("--category", default="policy", help="Category for incremental documents")
    
    args = parser.parse_args()
    
    logger.info("Starting ChromaDB data management...")
    
    # Incremental mode: Add new files without resetting
    if args.incremental:
        logger.info(f"Running in INCREMENTAL mode - adding {len(args.incremental)} file(s)")
        success = add_documents_incremental(
            data_file_paths=args.incremental,
            category=args.category
        )
        
        if success:
            logger.info("✓ Documents added successfully!")
            print(f"\n✓ Added {len(args.incremental)} file(s) to existing collection")
            print("✓ You can now run the main RAG system with: python main.py")
        else:
            logger.error("Failed to add documents!")
            print("\n✗ Failed to add documents. Please check the logs for errors.")
            exit(1)
    
    # Full initialization mode
    else:
        logger.info("Running in INITIALIZATION mode")
        success = initialize_chromadb_data(
            data_file_path=args.data_file,
            reset_collection=args.reset
        )
        
        if success:
            logger.info("Data initialization completed successfully!")
            print("\n✓ ChromaDB has been initialized with privacy policy data")
            print("✓ You can now run the main RAG system with: python main.py")
        else:
            logger.error("Data initialization failed!")
            print("\n✗ Data initialization failed. Please check the logs for errors.")
            exit(1)

if __name__ == "__main__":
    main()

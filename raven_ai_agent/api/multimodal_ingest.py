"""
Multimodal Ingest - Phase 4
Extract information from images, PDFs, and other files

Phase 4 of Memory Enhancement Project
"""
import frappe
import base64
import requests
from typing import Dict, List, Optional
from io import BytesIO


class MultimodalIngest:
    """
    Handle multimodal memory ingestion
    Supports: Images (PNG, JPG, GIF, WEBP), PDF, Audio, Video
    """
    
    SUPPORTED_TYPES = {
        # Images
        'image/png': 'image',
        'image/jpeg': 'image', 
        'image/gif': 'image',
        'image/webp': 'image',
        # Documents
        'application/pdf': 'pdf',
        # Audio
        'audio/mpeg': 'audio',
        'audio/wav': 'audio',
        'audio/ogg': 'audio',
        # Video
        'video/mp4': 'video',
        'video/webm': 'video',
    }
    
    def __init__(self, user: str = None):
        self.user = user
        self.client = None
        self._init_client()
    
    def _init_client(self):
        """Initialize LLM client with vision support"""
        try:
            from openai import OpenAI
            settings = frappe.get_doc("AI Agent Settings")
            api_key = settings.get_password("api_key")
            base_url = settings.get("base_url") or "https://api.openai.com/v1"
            self.client = OpenAI(api_key=api_key, base_url=base_url)
        except Exception as e:
            frappe.logger().error(f"MultimodalIngest: Failed to init client: {e}")
    
    def ingest_file(self, file_data: str, file_type: str, content: str = None) -> Dict:
        """
        Main entry point for file ingestion
        
        Args:
            file_data: Base64 encoded file content or URL
            file_type: MIME type of the file
            content: Optional text description/context
        
        Returns:
            Dict with extracted text, entities, topics, summary
        """
        category = self.SUPPORTED_TYPES.get(file_type, 'unknown')
        
        if category == 'unknown':
            return {"error": f"Unsupported file type: {file_type}"}
        
        if category == 'image':
            return self._process_image(file_data, content)
        elif category == 'pdf':
            return self._process_pdf(file_data, content)
        elif category == 'audio':
            return self._process_audio(file_data, content)
        elif category == 'video':
            return self._process_video(file_data, content)
        
        return {"error": "Processing failed"}
    
    def _process_image(self, image_data: str, context: str = None) -> Dict:
        """Process image using vision-capable LLM"""
        if not self.client:
            return {"error": "LLM client not initialized"}
        
        # Determine if image_data is URL or base64
        if image_data.startswith('http'):
            image_url = image_data
        else:
            image_url = f"data:image/jpeg;base64,{image_data}"
        
        prompt = f"""Analyze this image and extract:
1. A brief description of what's in the image
2. Any text visible in the image (OCR)
3. Key entities (people, places, objects)
4. Relevant topics/themes

Context: {context or 'No additional context'}

Respond with JSON:
{{
    "description": "<brief description>",
    "extracted_text": "<any text from image>",
    "entities": "<comma-separated entities>",
    "topics": "<comma-separated topics>",
    "summary": "<2-3 sentence summary>"
}}"""
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o",  # Vision-capable model
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": image_url}}
                        ]
                    }
                ],
                max_tokens=1000,
                temperature=0.3
            )
            
            result_text = response.choices[0].message.content
            return self._parse_json_response(result_text)
            
        except Exception as e:
            frappe.logger().error(f"Image processing error: {e}")
            return {"error": str(e)}
    
    def _process_pdf(self, pdf_data: str, context: str = None) -> Dict:
        """Process PDF document"""
        # For PDFs, we'd typically use a PDF parsing library
        # Here we use a simple approach with OCR or text extraction
        
        prompt = f"""Extract and analyze content from this PDF document.

Context: {context or 'No additional context'}

Extract:
1. Main topics discussed
2. Key entities (people, companies, dates)
3. Important facts or data
4. A brief summary

Respond with JSON:
{{
    "topics": "<comma-separated topics>",
    "entities": "<comma-separated entities>",
    "key_facts": "<important facts>",
    "summary": "<2-3 sentence summary>"
}}"""
        
        # Note: For actual PDF processing, you'd use a PDF library
        # This is a placeholder that would integrate with PDF extraction
        return {
            "prompt": prompt,
            "status": "PDF processing requires additional setup",
            "suggestion": "Use pdf2image + OCR or PDF parsing library"
        }
    
    def _process_audio(self, audio_data: str, context: str = None) -> Dict:
        """Process audio file (transcription)"""
        prompt = f"""Transcribe and analyze this audio file.

Context: {context or 'No additional context'}

Extract:
1. Main topics discussed
2. Key entities mentioned
3. Important statements or decisions
4. A brief summary

Respond with JSON:
{{
    "transcript": "<full or partial transcript>",
    "topics": "<comma-separated topics>",
    "entities": "<comma-separated entities>",
    "summary": "<2-3 sentence summary>"
}}"""
        
        return {
            "prompt": prompt,
            "status": "Audio processing requires Whisper API integration",
            "suggestion": "Use OpenAI Whisper for transcription"
        }
    
    def _process_video(self, video_data: str, context: str = None) -> Dict:
        """Process video file"""
        prompt = f"""Analyze this video and extract key information.

Context: {context or 'No additional context'}

Extract:
1. What's happening in the video
2. Any text or speech
3. Key entities
4. Main topics
5. Brief summary

Respond with JSON:
{{
    "description": "<scene description>",
    "extracted_text": "<any text or speech>",
    "topics": "<comma-separated topics>",
    "entities": "<comma-separated entities>",
    "summary": "<2-3 sentence summary>"
}}"""
        
        return {
            "prompt": prompt,
            "status": "Video processing requires frame extraction + vision",
            "suggestion": "Extract key frames and process as images"
        }
    
    def _parse_json_response(self, response_text: str) -> Dict:
        """Parse JSON from LLM response"""
        import json
        try:
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                return json.loads(response_text[json_start:json_end])
        except json.JSONDecodeError:
            pass
        return {"raw_response": response_text}
    
    def store_multimodal_memory(self, file_data: str, file_type: str, 
                                content: str = None, importance: str = "Normal") -> str:
        """
        Store extracted information as a memory
        
        Returns: memory name
        """
        result = self.ingest_file(file_data, file_type, content)
        
        if "error" in result:
            frappe.logger().error(f"Multimodal ingest failed: {result['error']}")
            return None
        
        # Build memory content
        memory_content = []
        if result.get("description"):
            memory_content.append(f"Description: {result['description']}")
        if result.get("extracted_text"):
            memory_content.append(f"Text: {result['extracted_text']}")
        if result.get("summary"):
            memory_content.append(f"Summary: {result['summary']}")
        
        full_content = "\n".join(memory_content)
        
        # Store via MemoryMixin
        # Get importance score from analysis
        importance_score = 0.5  # Default
        
        doc = frappe.get_doc({
            "doctype": "AI Memory",
            "user": self.user,
            "content": full_content,
            "importance": importance,
            "importance_score": importance_score,
            "entities": result.get("entities", ""),
            "topics": result.get("topics", ""),
            "memory_type": "Fact",
            "source": f"Multimedia ({file_type})"
        })
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        
        return doc.name


def ingest_file_via_api(file_content: str, file_type: str, user: str, 
                        content: str = None) -> Dict:
    """
    API function for file ingestion
    
    Usage:
    POST /api/method/raven_ai_agent.api.memory_manager.ingest_file_via_api
    {
        "file_content": "base64 or url",
        "file_type": "image/jpeg",
        "user": "user@example.com",
        "content": "optional context"
    }
    """
    ingest = MultimodalIngest(user=user)
    result = ingest.ingest_file(file_content, file_type, content)
    
    # Also store as memory
    if "error" not in result:
        memory_name = ingest.store_multimodal_memory(file_content, file_type, content)
        result["memory_name"] = memory_name
    
    return result

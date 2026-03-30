"""
EPUB to PubPub Chapter Splitter
Extracts individual chapters from an EPUB file and prepares them for PubPub import

Installation:
    pip install ebooklib beautifulsoup4 lxml

Usage:
    python epub_splitter.py
"""

import os
import re
from pathlib import Path
from ebooklib import epub
from bs4 import BeautifulSoup
import json
import base64
from PIL import Image
from io import BytesIO

class EPUBChapterSplitter:
    def __init__(self, epub_path, output_dir):
        self.epub_path = Path(epub_path)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.book = None
        self.chapters = []
        self.metadata = {}
        self.images = {}  # Add this to store image data
        self.image_map = {}  # Maps image references to chapter numbers
    
    def extract_images(self):
        """Extract all images from EPUB and organize by chapter"""
        print(f"\n  Extracting images...")
        
        images_dir = self.output_dir / "images"
        images_dir.mkdir(exist_ok=True)
        
        image_count = 0
        
        # Get all image items
        for item in self.book.get_items():
            try:
                is_image = item.get_type() == epub.ITEM_IMAGE
            except AttributeError:
                is_image = item.get_type() == 2  # ITEM_IMAGE constant
            
            if is_image:
                # Get image data
                image_data = item.get_content()
                image_name = os.path.basename(item.get_name())
                
                # Store image data and name
                self.images[item.get_name()] = {
                    'data': image_data,
                    'filename': image_name,
                    'content_type': item.media_type
                }
                
                image_count += 1
        
        print(f"  ✅ Found {image_count} images")
        return image_count
    
    def map_images_to_chapters(self):
        """Map which images belong to which chapters"""
        print(f"\n🔗 Mapping images to chapters...")
        
        for chapter in self.chapters:
            soup = BeautifulSoup(chapter['html_content'], 'html.parser')
            img_tags = soup.find_all('img')
            
            chapter['images'] = []
            
            for img in img_tags:
                src = img.get('src', '')
                alt = img.get('alt', '')
                
                # Find the image in our extracted images
                for img_path, img_data in self.images.items():
                    if img_data['filename'] in src or src in img_path:
                        chapter['images'].append({
                            'original_src': src,
                            'filename': img_data['filename'],
                            'alt': alt,
                            'img_path': img_path
                        })
                        
                        # Track which chapters use this image
                        if img_path not in self.image_map:
                            self.image_map[img_path] = []
                        self.image_map[img_path].append(chapter['number'])
        
        # Summary
        chapters_with_images = sum(1 for ch in self.chapters if ch['images'])
        print(f"  ✅ {chapters_with_images} chapters contain images")
    
    def save_images_by_chapter(self):
        """Save images organized by chapter folders"""
        print(f"\n💾 Saving images organized by chapter...")
        
        images_base = self.output_dir / "images"
        
        for chapter in self.chapters:
            if not chapter['images']:
                continue
            
            # Create chapter-specific image folder
            chapter_num = f"{chapter['number']:02d}"
            chapter_img_dir = images_base / f"chapter-{chapter_num}"
            chapter_img_dir.mkdir(parents=True, exist_ok=True)
            
            for idx, img_info in enumerate(chapter['images'], 1):
                img_path = img_info['img_path']
                img_data = self.images[img_path]
                
                # Create descriptive filename
                original_name = Path(img_data['filename']).stem
                extension = Path(img_data['filename']).suffix
                new_filename = f"{chapter_num}_{idx:02d}_{original_name}{extension}"
                
                # Save image file
                output_path = chapter_img_dir / new_filename
                with open(output_path, 'wb') as f:
                    f.write(img_data['data'])
                
                # Update image info with new path
                img_info['saved_path'] = str(output_path.relative_to(self.output_dir))
                img_info['new_filename'] = new_filename
            
            print(f"  ✅ Chapter {chapter_num}: {len(chapter['images'])} images")
    
    def save_images_as_base64(self):
        """Optional: Save base64-encoded images for embedding"""
        print(f"\n🔐 Generating Base64 encoded images...")
        
        base64_dir = self.output_dir / "images-base64"
        base64_dir.mkdir(exist_ok=True)
        
        base64_data = {}
        
        for img_path, img_data in self.images.items():
            # Encode to base64
            b64_string = base64.b64encode(img_data['data']).decode('utf-8')
            
            # Create data URL
            mime_type = img_data['content_type']
            data_url = f"data:{mime_type};base64,{b64_string}"
            
            base64_data[img_data['filename']] = data_url
        
        # Save as JSON for easy reference
        import json
        with open(base64_dir / "base64-images.json", 'w') as f:
            json.dump(base64_data, f, indent=2)
        
        print(f"  ✅ Saved base64 encodings for {len(base64_data)} images")
        return base64_data
    
    def update_chapter_image_references(self, use_base64=False, base64_data=None):
        """Update image src attributes in chapter HTML"""
        print(f"\n🔄 Updating image references in chapters...")
        
        for chapter in self.chapters:
            if not chapter['images']:
                continue
            
            soup = BeautifulSoup(chapter['html_content'], 'html.parser')
            img_tags = soup.find_all('img')
            
            for img_tag in img_tags:
                src = img_tag.get('src', '')
                
                # Find matching image in chapter
                for img_info in chapter['images']:
                    if img_info['original_src'] == src:
                        if use_base64 and base64_data:
                            # Use base64 data URL
                            new_src = base64_data.get(img_info['filename'], src)
                        else:
                            # Use relative path to saved image
                            new_src = f"../{img_info['saved_path']}"
                        
                        img_tag['src'] = new_src
                        break
            
            # Update chapter HTML content
            chapter['html_content'] = str(soup)
    
    def run(self, output_format='html', embed_images_base64=False):
        """Run the complete extraction process"""
        print("="*70)
        print("📚 EPUB to PubPub Chapter Splitter")
        print("="*70)
        
        # Load EPUB
        if not self.load_epub():
            return False
        
        # Extract images first
        self.extract_images()
        
        # Extract chapters
        chapters = self.extract_chapters()
        if not chapters:
            print("❌ No chapters found!")
            return False
        
        # Map images to chapters
        self.map_images_to_chapters()
        
        # Save images
        self.save_images_by_chapter()
        
        # Optional: Generate base64 versions
        base64_data = None
        if embed_images_base64:
            base64_data = self.save_images_as_base64()
        
        # Update image references in chapters
        self.update_chapter_image_references(
            use_base64=embed_images_base64,
            base64_data=base64_data
        )
        
        # Save chapters (now with updated image paths)
        self.save_chapters(format=output_format)
        
        # Create TOC
        self.create_table_of_contents()
        
        # Create import guide
        self.create_pubpub_import_guide()
        
        # Summary
        print("\n" + "="*70)
        print("✅ EXTRACTION COMPLETE!")
        print("="*70)
        print(f"📁 Output directory: {self.output_dir.absolute()}")
        print(f"📖 Total chapters: {len(self.chapters)}")
        print(f"🖼️  Total images: {len(self.images)}")
        print(f"📄 Files created:")
        print(f"   - {len(self.chapters)} chapter HTML files")
        print(f"   - {len(self.images)} images (organized by chapter)")
        if embed_images_base64:
            print(f"   - Base64 encoded images in images-base64/")
        print(f"   - table-of-contents.json")
        print(f"   - TABLE-OF-CONTENTS.md")
        print(f"   - PUBPUB-IMPORT-GUIDE.md")
        
        return True
    
    def load_epub(self):
        """Load the EPUB file"""
        print(f"\n📚 Loading EPUB: {self.epub_path.name}")
        
        try:
            self.book = epub.read_epub(str(self.epub_path))
            
            # Extract metadata
            self.metadata = {
                "title": self.book.get_metadata('DC', 'title')[0][0] if self.book.get_metadata('DC', 'title') else "Unknown",
                "author": self.book.get_metadata('DC', 'creator')[0][0] if self.book.get_metadata('DC', 'creator') else "Unknown",
                "language": self.book.get_metadata('DC', 'language')[0][0] if self.book.get_metadata('DC', 'language') else "en",
                "publisher": self.book.get_metadata('DC', 'publisher')[0][0] if self.book.get_metadata('DC', 'publisher') else "",
                "date": self.book.get_metadata('DC', 'date')[0][0] if self.book.get_metadata('DC', 'date') else "",
            }
            
            print(f"✅ Title: {self.metadata['title']}")
            print(f"✅ Author: {self.metadata['author']}")
            print(f"✅ Language: {self.metadata['language']}")
            
            return True
            
        except Exception as e:
            print(f"❌ Error loading EPUB: {e}")
            return False
    
    def extract_chapters(self):
        """Extract all chapters from the EPUB"""
        print(f"\n📖 Extracting chapters...")
        
        chapter_num = 1
        
        # Get all items from the book
        for item in self.book.get_items():
            # Only process HTML/XHTML documents
            # Handle different ebooklib versions
            try:
                is_document = item.get_type() == epub.ITEM_DOCUMENT
            except AttributeError:
                # Fallback for older versions
                is_document = item.get_type() == 9  # ITEM_DOCUMENT constant value
            
            if is_document:
                # Parse the HTML content
                soup = BeautifulSoup(item.get_content(), 'html.parser')
                
                # Try to extract chapter title
                chapter_title = self._extract_chapter_title(soup, item)
                
                # Get the text content
                text_content = soup.get_text(separator='\n', strip=True)
                
                # Skip if empty or very short (likely not a chapter)
                if len(text_content) < 100:
                    print(f"  ⏭️  Skipping short section: {chapter_title}")
                    continue
                
                # Create chapter data
                chapter = {
                    "number": chapter_num,
                    "title": chapter_title,
                    "filename": item.get_name(),
                    "html_content": str(soup),
                    "text_content": text_content,
                    "word_count": len(text_content.split())
                }
                
                self.chapters.append(chapter)
                print(f"  ✅ Chapter {chapter_num}: {chapter_title} ({chapter['word_count']} words)")
                chapter_num += 1
        
        print(f"\n📊 Total chapters extracted: {len(self.chapters)}")
        return self.chapters
    
    def _extract_chapter_title(self, soup, item):
        """Try to extract chapter title from various sources"""
        
        # Method 1: Look for h1, h2, h3 tags
        for tag in ['h1', 'h2', 'h3']:
            heading = soup.find(tag)
            if heading and heading.get_text(strip=True):
                return heading.get_text(strip=True)
        
        # Method 2: Look for title tag
        title_tag = soup.find('title')
        if title_tag and title_tag.get_text(strip=True):
            return title_tag.get_text(strip=True)
        
        # Method 3: Use filename
        filename = Path(item.get_name()).stem
        # Clean up filename (remove numbers, underscores, etc.)
        cleaned = re.sub(r'[_-]', ' ', filename)
        cleaned = re.sub(r'\d+', '', cleaned).strip()
        if cleaned:
            return cleaned.title()
        
        # Method 4: Default to "Chapter N"
        return f"Chapter {len(self.chapters) + 1}"
    
    def save_chapters(self, format='html'):
        """Save each chapter as individual files"""
        print(f"\n💾 Saving chapters as {format.upper()} files...")
        
        chapters_dir = self.output_dir / "chapters"
        chapters_dir.mkdir(exist_ok=True)
        
        for chapter in self.chapters:
            # Create filename
            safe_title = re.sub(r'[^\w\s-]', '', chapter['title'])
            safe_title = re.sub(r'[\s_]+', '-', safe_title).lower()
            filename = f"{chapter['number']:02d}_{safe_title}.{format}"
            filepath = chapters_dir / filename
            
            # Save based on format
            if format == 'html':
                content = self._create_html_document(chapter)
            elif format == 'markdown':
                content = self._convert_to_markdown(chapter)
            elif format == 'txt':
                content = chapter['text_content']
            else:
                content = chapter['html_content']
            
            # Write file
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            
            print(f"  ✅ Saved: {filename}")
    
    def _create_html_document(self, chapter):
        """Create a clean HTML document for a chapter"""
        html_template = f"""<!DOCTYPE html>
<html lang="{self.metadata['language']}">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{chapter['title']} - {self.metadata['title']}</title>
    <style>
        body {{
            max-width: 800px;
            margin: 0 auto;
            padding: 2rem;
            font-family: Georgia, serif;
            line-height: 1.6;
        }}
        h1, h2, h3 {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        }}
        .chapter-info {{
            color: #666;
            font-style: italic;
            margin-bottom: 2rem;
        }}
    </style>
</head>
<body>
    <h1>{chapter['title']}</h1>
    <div class="chapter-info">
        From "{self.metadata['title']}" by {self.metadata['author']}
    </div>
    <div class="content">
        {chapter['html_content']}
    </div>
</body>
</html>"""
        return html_template
    
    def _convert_to_markdown(self, chapter):
        """Convert chapter to Markdown format"""
        soup = BeautifulSoup(chapter['html_content'], 'html.parser')
        
        # Start with title
        markdown = f"# {chapter['title']}\n\n"
        markdown += f"*From \"{self.metadata['title']}\" by {self.metadata['author']}*\n\n"
        markdown += "---\n\n"
        
        # Convert HTML to basic Markdown
        for element in soup.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'blockquote']):
            text = element.get_text(strip=True)
            
            if element.name == 'h1':
                markdown += f"# {text}\n\n"
            elif element.name == 'h2':
                markdown += f"## {text}\n\n"
            elif element.name == 'h3':
                markdown += f"### {text}\n\n"
            elif element.name == 'h4':
                markdown += f"#### {text}\n\n"
            elif element.name == 'blockquote':
                markdown += f"> {text}\n\n"
            elif element.name == 'p':
                markdown += f"{text}\n\n"
        
        return markdown
    
    def create_table_of_contents(self):
        """Create a table of contents for PubPub import"""
        print(f"\n📋 Creating Table of Contents...")
        
        toc = {
            "book_info": self.metadata,
            "total_chapters": len(self.chapters),
            "chapters": []
        }
        
        for chapter in self.chapters:
            safe_title = re.sub(r'[^\w\s-]', '', chapter['title'])
            safe_title = re.sub(r'[\s_]+', '-', safe_title).lower()
            
            toc["chapters"].append({
                "number": chapter["number"],
                "title": chapter["title"],
                "slug": f"{chapter['number']:02d}_{safe_title}",
                "word_count": chapter["word_count"],
                "filename": f"{chapter['number']:02d}_{safe_title}.html"
            })
        
        # Save TOC
        toc_path = self.output_dir / "table-of-contents.json"
        with open(toc_path, 'w', encoding='utf-8') as f:
            json.dump(toc, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Saved table of contents: {toc_path.name}")
        
        # Also create a Markdown TOC
        md_toc = f"# {self.metadata['title']}\n"
        md_toc += f"*by {self.metadata['author']}*\n\n"
        md_toc += "## Table of Contents\n\n"
        
        for chapter in toc["chapters"]:
            md_toc += f"{chapter['number']}. [{chapter['title']}]({chapter['filename']}) ({chapter['word_count']} words)\n"
        
        md_toc_path = self.output_dir / "TABLE-OF-CONTENTS.md"
        with open(md_toc_path, 'w', encoding='utf-8') as f:
            f.write(md_toc)
        
        print(f"✅ Saved Markdown TOC: {md_toc_path.name}")
        
        return toc
    
    def create_pubpub_import_guide(self):
        """Create a guide for importing into PubPub"""
        guide = f"""# PubPub Import Guide for "{self.metadata['title']}"

## Overview
- **Book:** {self.metadata['title']}
- **Author:** {self.metadata['author']}
- **Total Chapters:** {len(self.chapters)}

## Import Steps

### 1. Create a Collection in PubPub
1. Go to your PubPub community
2. Click "Create Collection"
3. Name it: "{self.metadata['title']}"
4. Add description and metadata

### 2. Import Each Chapter as a Publication
For each chapter file in the `chapters/` directory:

1. Click "Create Pub" in your collection
2. Give it the chapter title (from table-of-contents.json)
3. Import the HTML file or copy/paste the content
4. Set the slug to match the filename (e.g., `01-chapter-one`)
5. Publish when ready

### 3. Create Table of Contents Pub
1. Create a special publication called "Table of Contents"
2. Copy content from `TABLE-OF-CONTENTS.md`
3. Link to each chapter using PubPub's internal linking
4. Pin this to the top of your collection

### 4. Order the Publications
Use PubPub's collection ordering to arrange chapters in sequence.

## Chapter List
"""
        
        for chapter in self.chapters:
            guide += f"\n### Chapter {chapter['number']}: {chapter['title']}\n"
            guide += f"- **File:** `chapters/{chapter['number']:02d}_*.html`\n"
            guide += f"- **Word Count:** {chapter['word_count']}\n"
        
        guide_path = self.output_dir / "PUBPUB-IMPORT-GUIDE.md"
        with open(guide_path, 'w', encoding='utf-8') as f:
            f.write(guide)
        
        print(f"✅ Saved import guide: {guide_path.name}")
    
    def run(self, output_format='html'):
        """Run the complete extraction process"""
        print("="*70)
        print("📚 EPUB to PubPub Chapter Splitter")
        print("="*70)
        
        # Load EPUB
        if not self.load_epub():
            return False
        
        # Extract chapters
        chapters = self.extract_chapters()
        if not chapters:
            print("❌ No chapters found!")
            return False
        
        # Save chapters
        self.save_chapters(format=output_format)
        
        # Create TOC
        self.create_table_of_contents()
        
        # Create import guide
        self.create_pubpub_import_guide()
        
        # Summary
        print("\n" + "="*70)
        print("✅ EXTRACTION COMPLETE!")
        print("="*70)
        print(f"📁 Output directory: {self.output_dir.absolute()}")
        print(f"📖 Total chapters: {len(self.chapters)}")
        print(f"📄 Files created:")
        print(f"   - {len(self.chapters)} chapter HTML files")
        print(f"   - table-of-contents.json")
        print(f"   - TABLE-OF-CONTENTS.md")
        print(f"   - PUBPUB-IMPORT-GUIDE.md")
        print(f"\n💡 Next steps:")
        print(f"   1. Review the chapters in the 'chapters/' directory")
        print(f"   2. Read PUBPUB-IMPORT-GUIDE.md for import instructions")
        print(f"   3. Import each chapter into PubPub as a separate publication")
        
        return True


def main():
    print("="*70)
    print("📚 EPUB to PubPub Chapter Splitter")
    print("="*70)
    
    # Get EPUB file
    print("\nStep 1: Locate your EPUB file")
    epub_path = input("Enter the path to your EPUB file: ").strip()
    
    # Remove quotes if user dragged file
    epub_path = epub_path.strip('"').strip("'")
    
    if not os.path.exists(epub_path):
        print(f"❌ File not found: {epub_path}")
        return
    
    # Get output directory
    print("\nStep 2: Choose output directory")
    default_output = Path.home() / "Desktop" / "Frankenstein-PubPub"
    print(f"Default: {default_output}")
    
    custom_output = input("Press Enter for default, or enter custom path: ").strip()
    output_dir = Path(custom_output) if custom_output else default_output
    
    # Choose format
    print("\nStep 3: Choose output format")
    print("  1. HTML (recommended for PubPub)")
    print("  2. Markdown")
    print("  3. Plain text")
    
    format_choice = input("Enter choice (1-3, default 1): ").strip() or "1"
    format_map = {"1": "html", "2": "markdown", "3": "txt"}
    output_format = format_map.get(format_choice, "html")
    
    # Confirmation
    print(f"\n📋 Configuration:")
    print(f"   EPUB file: {epub_path}")
    print(f"   Output directory: {output_dir}")
    print(f"   Format: {output_format.upper()}")
    
    confirm = input("\nProceed? (y/n): ").strip().lower()
    if confirm != 'y':
        print("Cancelled.")
        return
    
    # Run the splitter
    splitter = EPUBChapterSplitter(epub_path, output_dir)
    splitter.run(output_format=output_format)

    # Choose format
    print("\nStep 3: Choose output format")
    print("  1. HTML (recommended for PubPub)")
    print("  2. Markdown")
    print("  3. Plain text")
    
    format_choice = input("Enter choice (1-3, default 1): ").strip() or "1"
    format_map = {"1": "html", "2": "markdown", "3": "txt"}
    output_format = format_map.get(format_choice, "html")
    
    # Ask about Base64 embedding
    print("\nStep 4: Image embedding")
    print("  Images will be saved in organized folders.")
    embed_base64 = input("Also create base64-embedded versions? (y/n, default n): ").strip().lower()
    use_base64 = embed_base64 == 'y'
    
    # ... confirmation and run ...
    splitter = EPUBChapterSplitter(epub_path, output_dir)
    splitter.run(output_format=output_format, embed_images_base64=use_base64)
    """

    **This adds:**
    - ✅ Extracts all images from EPUB
    - ✅ Organizes images in `images/chapter-01/`, `images/chapter-02/`, etc.
    - ✅ Names images descriptively: `01_01_illustration.jpg`, `01_02_diagram.png`
    - ✅ Updates image references in chapter HTML to point to saved files
    - ✅ Optional: Creates base64-encoded versions in `images-base64/`
    - ✅ Maps which images belong to which chapters
    - ✅ Shows summary of images per chapter
"""
"""
    **Folder structure output:**
    
    output_dir/
    ├── chapters/
    │   ├── 01_chapter-one.html
    │   ├── 02_chapter-two.html
    ├── images/
    │   ├── chapter-01/
    │   │   ├── 01_01_illustration.jpg
    │   │   └── 01_02_diagram.png
    │   ├── chapter-02/
    │   │   └── 02_01_map.jpg
    ├── images-base64/ (if enabled)
    │   └── base64-images.json
    ├── table-of-contents.json
    └── PUBPUB-IMPORT-GUIDE.md
   """

if __name__ == "__main__":
    # Install: pip install ebooklib beautifulsoup4 lxml
    main()
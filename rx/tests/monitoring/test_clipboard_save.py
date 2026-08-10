"""Tests for clipboard save functionality in ClipSubject."""
import os
import tempfile
import pytest

from vools.reactive.monitoring.clipboard import (
    ClipSubject,
    ClipChangeType,
)


class TestClipboardSave:
    """Test clipboard save functionality."""

    def test_save_clips_text_to_file_with_text(self):
        """Test saving text clipboard content to file."""
        with ClipSubject(backend="polling", interval=0.1) as subject:
            subject.set_text("test clipboard content")
            
            with tempfile.TemporaryDirectory() as tmpdir:
                result = subject.save_clips_text_to_file(output_dir=tmpdir)
                
                assert result is True
                
                files = os.listdir(tmpdir)
                assert len(files) == 1
                assert files[0].startswith("clip_") and files[0].endswith(".txt")
                
                with open(os.path.join(tmpdir, files[0]), "r", encoding="utf-8") as f:
                    content = f.read()
                    assert content == "test clipboard content"

    def test_save_clips_text_to_file_with_filter(self):
        """Test saving text with regex filter."""
        with ClipSubject(backend="polling", interval=0.1) as subject:
            subject.set_text("hello world")
            
            with tempfile.TemporaryDirectory() as tmpdir:
                result = subject.save_clips_text_to_file(
                    reg_pattern="hello",
                    output_dir=tmpdir
                )
                
                assert result is True
                
                files = os.listdir(tmpdir)
                assert len(files) == 1

    def test_save_clips_text_to_file_filter_mismatch(self):
        """Test saving text when regex filter doesn't match."""
        with ClipSubject(backend="polling", interval=0.1) as subject:
            subject.set_text("hello world")
            
            with tempfile.TemporaryDirectory() as tmpdir:
                result = subject.save_clips_text_to_file(
                    reg_pattern="goodbye",
                    output_dir=tmpdir
                )
                
                assert result is False
                
                files = os.listdir(tmpdir)
                assert len(files) == 0

    def test_save_clips_text_to_file_invalid_regex(self):
        """Test saving text with invalid regex pattern."""
        with ClipSubject(backend="polling", interval=0.1) as subject:
            subject.set_text("test content")
            
            with tempfile.TemporaryDirectory() as tmpdir:
                result = subject.save_clips_text_to_file(
                    reg_pattern="[invalid",
                    output_dir=tmpdir
                )
                
                assert result is False

    def test_save_clips_text_to_file_save_to_one(self):
        """Test saving text to a single file."""
        with ClipSubject(backend="polling", interval=0.1) as subject:
            subject.set_text("test content")
            
            with tempfile.TemporaryDirectory() as tmpdir:
                result = subject.save_clips_text_to_file(
                    save_to_one_file=True,
                    output_dir=tmpdir
                )
                
                assert result is True
                
                files = os.listdir(tmpdir)
                assert len(files) == 1
                assert files[0].startswith("clip_text_")

    def test_save_clips_text_to_file_no_text(self):
        """Test saving when clipboard has no text (has image instead)."""
        with ClipSubject(backend="polling", interval=0.1) as subject:
            subject.set_bytes(b"image data")
            
            with tempfile.TemporaryDirectory() as tmpdir:
                result = subject.save_clips_text_to_file(output_dir=tmpdir)
                
                assert result is False

    def test_save_all_to_file_text(self):
        """Test save_all_to_file with text content."""
        with ClipSubject(backend="polling", interval=0.1) as subject:
            subject.set_text("test all content")
            
            with tempfile.TemporaryDirectory() as tmpdir:
                result = subject.save_all_to_file(output_dir=tmpdir)
                
                assert result is True
                
                files = os.listdir(tmpdir)
                assert len(files) == 1
                assert files[0].endswith(".txt")

    def test_save_all_to_file_with_custom_extensions(self):
        """Test save_all_to_file with custom extensions."""
        with ClipSubject(backend="polling", interval=0.1) as subject:
            subject.set_text("test content")
            
            with tempfile.TemporaryDirectory() as tmpdir:
                result = subject.save_all_to_file(
                    text_extension=".md",
                    output_dir=tmpdir
                )
                
                assert result is True
                
                files = os.listdir(tmpdir)
                assert len(files) == 1
                assert files[0].endswith(".md")

    def test_save_all_to_file_no_content(self):
        """Test save_all_to_file when clipboard has text (not image or files)."""
        with ClipSubject(backend="polling", interval=0.1) as subject:
            subject.set_text("text content")
            
            with tempfile.TemporaryDirectory() as tmpdir:
                result = subject.save_all_to_file(output_dir=tmpdir)
                
                assert result is True
                
                files = os.listdir(tmpdir)
                assert len(files) == 1
                assert files[0].endswith(".txt")

    def test_save_clips_picture_to_file_no_image(self):
        """Test save_clips_picture_to_file when clipboard has no image."""
        with ClipSubject(backend="polling", interval=0.1) as subject:
            subject.set_text("not an image")
            
            with tempfile.TemporaryDirectory() as tmpdir:
                result = subject.save_clips_picture_to_file(output_dir=tmpdir)
                
                assert result is False

    def test_save_clips_picture_to_file_with_bytes(self):
        """Test save_clips_picture_to_file with bytes content (image type)."""
        with ClipSubject(backend="polling", interval=0.1) as subject:
            subject.set_bytes(b"fake image data")
            
            with tempfile.TemporaryDirectory() as tmpdir:
                result = subject.save_clips_picture_to_file(output_dir=tmpdir)
                
                assert result is True
                
                files = os.listdir(tmpdir)
                assert len(files) == 1
                assert files[0].startswith("clip_image_")

    def test_save_all_to_file_bytes(self):
        """Test save_all_to_file with bytes content (image type)."""
        with ClipSubject(backend="polling", interval=0.1) as subject:
            subject.set_bytes(b"test bytes")
            
            with tempfile.TemporaryDirectory() as tmpdir:
                result = subject.save_all_to_file(output_dir=tmpdir)
                
                assert result is True
                
                files = os.listdir(tmpdir)
                assert len(files) == 1
                assert files[0].startswith("clip_image_")

    def test_save_clips_text_to_file_custom_extension(self):
        """Test save_clips_text_to_file with custom extension."""
        import time
        
        with ClipSubject(backend="polling", interval=0.1) as subject:
            subject.set_text("custom extension test")
            time.sleep(0.2)
            
            with tempfile.TemporaryDirectory() as tmpdir:
                result = subject.save_clips_text_to_file(
                    extension=".log",
                    output_dir=tmpdir
                )
                
                assert result is True
                
                files = os.listdir(tmpdir)
                assert len(files) == 1
                assert files[0].endswith(".log")

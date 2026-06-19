"""
Chunking utilities for AIRD preprocessing.

Ports sentence and character-based chunking from AIRD.
"""

from typing import List

import regex as re

# Sentence splitting regex
SENT_SPLIT_RE = re.compile(r"(?<!\b[A-Z])[.!?。۔؟]+(?=\s+[A-Z0-9\"'])")


def tokens_estimate(s: str) -> int:
    """Lightweight token count approximation."""
    return max(len(s) // 4, len(s.split()))


def char_chunk(text: str, max_tokens: int, overlap_chars: int) -> List[str]:
    """Character-based chunking with overlap."""
    out, start, max_chars = [], 0, max_tokens * 4
    L = len(text)
    while start < L:
        end = min(L, start + max_chars)
        piece = text[start:end].strip()
        if piece:
            out.append(piece)
        if end >= L:
            break
        start = max(end - overlap_chars, start + 1)
    return out


def sentence_chunk(body: str, max_tokens: int, overlap_sents: int, hard_overlap_chars: int) -> List[str]:
    """Sentence-based chunking with overlap, with improved handling of long sentences.

    This preserves semantic boundaries better than character-based chunking by respecting
    sentence boundaries and maintaining context within chunks. For sentences that exceed
    max_tokens, it attempts to split at word boundaries rather than mid-sentence.
    """
    sents = re.split(SENT_SPLIT_RE, body)
    sents = [s.strip() for s in sents if s and s.strip()]
    if not sents:
        return char_chunk(body, max_tokens, hard_overlap_chars)

    chunks, buf = [], []
    for s in sents:
        # Check if single sentence exceeds max_tokens
        sent_tokens = tokens_estimate(s)
        if sent_tokens > max_tokens:
            # Flush buffer first if it exists
            if buf:
                chunks.append(" ".join(buf))
                buf = []
            
            # For very long sentences, split at word boundaries (not mid-word)
            # This is better than char_chunk which can break mid-word
            long_sentence_chunks = _split_long_sentence_at_words(s, max_tokens, hard_overlap_chars)
            chunks.extend(long_sentence_chunks)
            # For overlap, keep the last chunk
            if long_sentence_chunks and overlap_sents > 0:
                buf = [long_sentence_chunks[-1]]
            else:
                buf = []
        else:
            cand = " ".join(buf + [s])
            if tokens_estimate(cand) <= max_tokens:
                buf.append(s)
            else:
                if buf:
                    chunks.append(" ".join(buf))
                # Keep last N sentences for overlap (preserve context)
                buf = buf[-overlap_sents:] if overlap_sents > 0 else []
                buf.append(s)
    
    if buf:
        chunks.append(" ".join(buf))

    # Final validation: ensure no chunk exceeds max_tokens
    # If any do, split at word boundaries (not mid-sentence)
    out: List[str] = []
    for c in chunks:
        if tokens_estimate(c) > max_tokens:
            # Split at word boundaries to avoid mid-sentence breaks
            out.extend(_split_long_sentence_at_words(c, max_tokens, hard_overlap_chars))
        else:
            out.append(c)
    return out


def _split_long_sentence_at_words(text: str, max_tokens: int, overlap_chars: int) -> List[str]:
    """Split a long sentence at word boundaries to avoid mid-word breaks.
    
    This is used when a single sentence exceeds max_tokens. It splits at word
    boundaries (spaces) rather than arbitrary character positions.
    """
    words = text.split()
    if not words:
        return [text]
    
    max_chars = max_tokens * 4  # Approximate chars per token
    chunks = []
    current_chunk = []
    current_length = 0
    
    for word in words:
        word_length = len(word) + 1  # +1 for space
        if current_length + word_length > max_chars and current_chunk:
            # Flush current chunk
            chunks.append(" ".join(current_chunk))
            # Start new chunk with overlap
            if overlap_chars > 0 and current_chunk:
                # Keep last few words for overlap
                overlap_words = []
                overlap_length = 0
                for w in reversed(current_chunk):
                    if overlap_length + len(w) + 1 <= overlap_chars:
                        overlap_words.insert(0, w)
                        overlap_length += len(w) + 1
                    else:
                        break
                current_chunk = overlap_words
                current_length = overlap_length
            else:
                current_chunk = []
                current_length = 0
        
        current_chunk.append(word)
        current_length += word_length
    
    if current_chunk:
        chunks.append(" ".join(current_chunk))
    
    return chunks if chunks else [text]


def paragraph_chunk(body: str, max_tokens: int, overlap_paras: int, hard_overlap_chars: int) -> List[str]:
    """Paragraph-based chunking with multi-heuristic detection for PDFs.

    Uses multiple strategies to detect paragraph boundaries:
    1. Double newlines (standard paragraph breaks)
    2. Indentation changes (common in PDFs)
    3. Line length heuristics (short lines often indicate breaks)
    4. Falls back to sentence chunking if paragraphs are too large or not found.

    This is critical for PDFs which often lack clear paragraph boundaries.
    """
    if not body or not body.strip():
        return []
    
    # Strategy 1: Split on double newlines (standard paragraph breaks)
    paras = re.split(r"\n\s*\n+", body)
    paras = [p.strip() for p in paras if p and p.strip()]
    
    # Strategy 2: If no clear paragraphs found, try indentation-based detection
    if len(paras) <= 1 or all(len(p) < 50 for p in paras):
        # Try to detect paragraphs by indentation changes
        lines = body.split("\n")
        para_groups = []
        current_para = []
        prev_indent = None
        
        for line in lines:
            stripped = line.strip()
            if not stripped:
                if current_para:
                    para_groups.append("\n".join(current_para))
                    current_para = []
                continue
            
            # Detect indentation (leading spaces)
            indent = len(line) - len(line.lstrip())
            
            # If indentation changes significantly, start new paragraph
            if prev_indent is not None and abs(indent - prev_indent) > 2:
                if current_para:
                    para_groups.append("\n".join(current_para))
                    current_para = [stripped]
                else:
                    current_para.append(stripped)
            else:
                current_para.append(stripped)
            
            prev_indent = indent
        
        if current_para:
            para_groups.append("\n".join(current_para))
        
        # Use indentation-based paragraphs if we found more than double-newline method
        if len(para_groups) > len(paras):
            paras = [p.strip() for p in para_groups if p and p.strip()]
    
    # Strategy 3: If still no good paragraphs, fall back to sentence chunking
    if not paras or (len(paras) == 1 and tokens_estimate(paras[0]) > max_tokens * 2):
        # No clear paragraph structure, use sentence chunking
        return sentence_chunk(body, max_tokens, max(1, overlap_paras * 2), hard_overlap_chars)

    chunks, buf = [], []
    for para in paras:
        cand = "\n\n".join(buf + [para]) if buf else para
        para_tokens = tokens_estimate(para)
        cand_tokens = tokens_estimate(cand)

        # If single paragraph exceeds max_tokens, use sentence chunking on it
        if para_tokens > max_tokens:
            # Flush buffer first if it exists
            if buf:
                chunks.append("\n\n".join(buf))
                buf = []
            # Use sentence chunking on this large paragraph to preserve sentence boundaries
            para_chunks = sentence_chunk(para, max_tokens, max(1, overlap_paras * 2), hard_overlap_chars)
            chunks.extend(para_chunks)
        elif cand_tokens <= max_tokens:
            # Can add to buffer
            buf.append(para)
        else:
            # Buffer + new para exceeds max, flush buffer
            if buf:
                chunks.append("\n\n".join(buf))
            # Keep last N paragraphs for overlap
            buf = buf[-overlap_paras:] if overlap_paras > 0 else []
            buf.append(para)

    if buf:
        chunks.append("\n\n".join(buf))

    # Final pass: ensure no chunk exceeds max_tokens (safety check)
    out: List[str] = []
    for c in chunks:
        if tokens_estimate(c) > max_tokens:
            # Use sentence chunking for oversized chunks to preserve sentence boundaries
            out.extend(sentence_chunk(c, max_tokens, max(1, overlap_paras * 2), hard_overlap_chars))
        else:
            out.append(c)
    return out

"""SQLite schema for thread-scoped life record storage."""

from __future__ import annotations


SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS students (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  school_name TEXT,
  class_no TEXT,
  student_no TEXT,
  birth_masked TEXT,
  profile_photo_path TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(name, school_name, birth_masked)
);
CREATE TABLE IF NOT EXISTS student_documents (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  student_id INTEGER NOT NULL REFERENCES students(id),
  document_type TEXT NOT NULL,
  source_pdf_path TEXT NOT NULL,
  stored_pdf_path TEXT NOT NULL,
  file_sha256 TEXT NOT NULL UNIQUE,
  page_count INTEGER NOT NULL,
  issued_at TEXT,
  issuer_school TEXT,
  document_number TEXT,
  verification_number TEXT,
  raw_text TEXT NOT NULL,
  metadata_json TEXT,
  extraction_method TEXT NOT NULL,
  extraction_confidence REAL NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS student_photos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  student_id INTEGER NOT NULL REFERENCES students(id),
  document_id INTEGER REFERENCES student_documents(id),
  image_path TEXT NOT NULL,
  source_page INTEGER NOT NULL,
  width INTEGER NOT NULL,
  height INTEGER NOT NULL,
  image_sha256 TEXT NOT NULL,
  is_primary INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS life_record_sections (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  student_document_id INTEGER NOT NULL REFERENCES student_documents(id),
  section_type TEXT NOT NULL,
  page_start INTEGER,
  page_end INTEGER,
  raw_text TEXT NOT NULL,
  parsed_json TEXT,
  confidence REAL NOT NULL,
  review_status TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS attendance_records (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  student_document_id INTEGER NOT NULL REFERENCES student_documents(id),
  grade INTEGER NOT NULL,
  school_days INTEGER,
  absent_disease INTEGER DEFAULT 0,
  absent_unexcused INTEGER DEFAULT 0,
  absent_other INTEGER DEFAULT 0,
  late_disease INTEGER DEFAULT 0,
  late_unexcused INTEGER DEFAULT 0,
  late_other INTEGER DEFAULT 0,
  early_leave_disease INTEGER DEFAULT 0,
  early_leave_unexcused INTEGER DEFAULT 0,
  early_leave_other INTEGER DEFAULT 0,
  result_disease INTEGER DEFAULT 0,
  result_unexcused INTEGER DEFAULT 0,
  result_other INTEGER DEFAULT 0,
  special_note TEXT,
  confidence REAL NOT NULL DEFAULT 0.80,
  review_status TEXT NOT NULL DEFAULT 'needs_review',
  created_at TEXT NOT NULL,
  UNIQUE(student_document_id, grade)
);
CREATE TABLE IF NOT EXISTS subject_grades (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  student_document_id INTEGER NOT NULL REFERENCES student_documents(id),
  grade INTEGER,
  semester INTEGER,
  category TEXT,
  subject TEXT NOT NULL,
  credits REAL,
  raw_score TEXT,
  achievement TEXT,
  students_count INTEGER,
  rank_grade TEXT,
  raw_row TEXT NOT NULL,
  confidence REAL NOT NULL DEFAULT 0.78,
  review_status TEXT NOT NULL DEFAULT 'needs_review',
  created_at TEXT NOT NULL,
  UNIQUE(student_document_id, grade, semester, subject)
);
CREATE TABLE IF NOT EXISTS subject_special_notes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  student_document_id INTEGER NOT NULL REFERENCES student_documents(id),
  grade INTEGER,
  semester INTEGER,
  subject TEXT NOT NULL,
  note_text TEXT NOT NULL,
  source_page_start INTEGER,
  source_page_end INTEGER,
  confidence REAL NOT NULL DEFAULT 0.80,
  review_status TEXT NOT NULL DEFAULT 'needs_review',
  created_at TEXT NOT NULL,
  UNIQUE(student_document_id, grade, semester, subject)
);
CREATE TABLE IF NOT EXISTS awards (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  student_document_id INTEGER NOT NULL REFERENCES student_documents(id),
  grade INTEGER,
  title TEXT NOT NULL,
  awarded_at TEXT,
  issuer TEXT,
  confidence REAL NOT NULL DEFAULT 0.80,
  review_status TEXT NOT NULL DEFAULT 'needs_review',
  created_at TEXT NOT NULL,
  UNIQUE(student_document_id, title, awarded_at)
);
CREATE TABLE IF NOT EXISTS extraction_audit_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  document_id INTEGER REFERENCES student_documents(id),
  method TEXT NOT NULL,
  version TEXT NOT NULL,
  result_summary TEXT NOT NULL,
  confidence_before REAL,
  confidence_after REAL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS verification_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  document_id INTEGER NOT NULL REFERENCES student_documents(id),
  round_name TEXT NOT NULL,
  status TEXT NOT NULL,
  summary_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);
"""


# Central student DB — confirmed records promoted from thread bundles, accumulated
# per student across semesters (1학년 → 2·3학년). Read-friendly for the assistant.
CENTRAL_SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS students (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  school_name TEXT,
  birth_masked TEXT,
  profile_photo_path TEXT,
  source_thread TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(name, school_name, birth_masked)
);
CREATE TABLE IF NOT EXISTS central_attendance (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  student_id INTEGER NOT NULL REFERENCES students(id),
  grade INTEGER NOT NULL,
  school_days INTEGER,
  detail_json TEXT,
  special_note TEXT,
  updated_at TEXT NOT NULL,
  UNIQUE(student_id, grade)
);
CREATE TABLE IF NOT EXISTS central_grades (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  student_id INTEGER NOT NULL REFERENCES students(id),
  grade INTEGER,
  semester INTEGER,
  category TEXT,
  subject TEXT NOT NULL,
  credits REAL,
  raw_score TEXT,
  achievement TEXT,
  students_count INTEGER,
  rank_grade TEXT,
  updated_at TEXT NOT NULL,
  UNIQUE(student_id, grade, semester, subject)
);
CREATE TABLE IF NOT EXISTS central_notes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  student_id INTEGER NOT NULL REFERENCES students(id),
  grade INTEGER,
  semester INTEGER,
  subject TEXT NOT NULL,
  note_text TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(student_id, grade, semester, subject)
);
CREATE TABLE IF NOT EXISTS central_awards (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  student_id INTEGER NOT NULL REFERENCES students(id),
  grade INTEGER,
  title TEXT NOT NULL,
  awarded_at TEXT,
  issuer TEXT,
  updated_at TEXT NOT NULL,
  UNIQUE(student_id, title, awarded_at)
);
CREATE TABLE IF NOT EXISTS central_promotions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  student_id INTEGER NOT NULL REFERENCES students(id),
  source_document_sha256 TEXT,
  source_thread TEXT,
  promoted_at TEXT NOT NULL
);
"""

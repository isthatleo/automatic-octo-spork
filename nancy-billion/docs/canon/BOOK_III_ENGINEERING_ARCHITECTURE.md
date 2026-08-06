# NÅNCY CANONICAL SPECIFICATION

# BOOK III — ENGINEERING ARCHITECTURE BIBLE

## Version 1.0

**Classification:** Canonical Engineering Constitution

**Status:** Source of Truth

> **Implementation note (2026-08-06):** the live `nancy-billion` codebase is Python/FastAPI, not the
> Rust/Axum + Postgres/Qdrant + monorepo architecture this book specifies, and has substantial real,
> working functionality (80 routed specialized agents, genuine agent-to-agent peer review, a real
> memory graph, live TradingView wiring, real Google Calendar OAuth). By explicit decision, this book
> is treated as long-term aspirational guidance -- its *principles* (modularity, replaceability,
> event-driven, API-first, AI-agnostic, sovereign) inform how new code is written -- rather than a
> literal migration target. No rewrite is in progress. See `CHANGELOG.md`, 2026-08-06 entry.

---

# PREFACE

Architecture is where software either becomes immortal or dies.

The purpose of this document is not merely to describe technologies.

Its purpose is to define an architecture capable of surviving decades of evolution.

NÅNCY should never be tightly coupled to a single AI model, cloud provider, framework, database, programming language, or hardware platform.

Every component should be replaceable.

Every service should be composable.

Every interface should be documented.

Every subsystem should evolve independently.

This document governs every engineering decision.

---

# CHAPTER 1

# ARCHITECTURAL PRINCIPLES

Every engineering decision must satisfy these principles.

## 1. Modularity

Every capability exists as an independent module.

Memory should not know how documents work.

Documents should not know how agents work.

Agents should not know database implementation.

Everything communicates through contracts.

---

## 2. Replaceability

Any subsystem can be replaced without rebuilding the entire platform.

Examples

Replace PostgreSQL

Replace Qdrant

Replace OpenAI

Replace Claude

Replace Gemini

Replace DeepSeek

Replace Ollama

Replace Whisper

Replace TTS

without rewriting NÅNCY.

---

## 3. Event Driven

Everything important generates events.

Examples

Memory Created

Project Updated

Agent Started

Agent Finished

Knowledge Linked

Document Indexed

Research Completed

Task Assigned

Conversation Summarized

Every event becomes observable.

---

## 4. API First

Everything must expose APIs.

Internal APIs.

External APIs.

Future SDKs.

Everything communicates through well-defined interfaces.

---

## 5. AI Agnostic

LLMs are engines.

Not architecture.

Architecture survives model changes.

---

## 6. Sovereign

The user owns everything.

Never architect around vendor lock-in.

---

# CHAPTER 2

# HIGH LEVEL SYSTEM

```text
                    USER

                     │

             Desktop / Mobile

                     │

──────────────────────────────────────────

              Frontend Layer

──────────────────────────────────────────

                     │

              Gateway API

                     │

──────────────────────────────────────────

         Core Intelligence Platform

──────────────────────────────────────────

Workspace

Memory

Knowledge

Documents

Agents

Reasoning

Planning

Search

Notifications

Authentication

Observability

Automation

──────────────────────────────────────────

        Intelligence Infrastructure

──────────────────────────────────────────

LLMs

Embeddings

OCR

Speech

Vision

Vector Search

──────────────────────────────────────────

          Persistence Layer

──────────────────────────────────────────

PostgreSQL

Redis

Qdrant

Object Storage

Event Store

Audit Store

──────────────────────────────────────────

       Infrastructure Platform

──────────────────────────────────────────

Docker

Kubernetes

GitHub Actions

Monitoring

Logging

Backups

```

---

# CHAPTER 3

# REPOSITORY ARCHITECTURE

The project should live in a single monorepo.

```text
nancy/

apps/
    desktop/
    web/
    mobile/
    landing/

services/
    api-gateway/
    auth/
    workspace/
    memory/
    knowledge/
    documents/
    search/
    planner/
    agents/
    reasoning/
    notifications/
    automation/
    analytics/
    ai-runtime/
    embeddings/
    voice/
    vision/
    integrations/

packages/
    ui/
    design-system/
    sdk/
    database/
    shared/
    events/
    auth/
    ai/
    telemetry/
    config/

docs/
    canonical/
    architecture/
    api/
    ui/
    database/

infrastructure/
docker/
terraform/
helm/

scripts/

.github/

```

---

# CHAPTER 4

# CLIENT APPLICATIONS

NÅNCY is not one application.

It is an ecosystem.

---

## Desktop

Primary experience.

Electron or Tauri.

Native integrations.

Filesystem.

Microphone.

Notifications.

GPU acceleration.

Offline capability.

---

## Web

Universal access.

Administration.

Collaboration.

Organization management.

---

## Mobile

Capture.

Memory.

Voice.

Notifications.

Quick research.

Daily briefings.

---

## Future

VisionOS

Android Auto

Apple CarPlay

Smart displays

Astronaut Companion

AR Glasses

---

# CHAPTER 5

# FRONTEND ARCHITECTURE

Stack

Next.js

TypeScript

TailwindCSS

shadcn/ui

React Query

Zustand

React Flow

Framer Motion

TipTap

Motion One

Three.js (for Intelligence Hub)

---

Feature Modules

Dashboard

Workspace

Projects

Chat

Memory

Knowledge

Documents

Agents

Planner

Settings

Marketplace

Administration

Developer

---

Each module owns

Pages

Components

Hooks

State

API client

Tests

Documentation

---

# CHAPTER 6

# DESIGN SYSTEM

Single source of truth.

Contains

Typography

Spacing

Icons

Animations

Tokens

Shadows

Borders

Motion

Glass

Depth

Glow

Particles

Orb behaviors

Interaction language

Dark mode

Light mode

Accessibility

---

# CHAPTER 7

# BACKEND ARCHITECTURE

Primary Language

Rust

Framework

Axum

Async Runtime

Tokio

---

Core Services

API Gateway

Authentication

Workspace

Memory

Knowledge

Planner

Documents

Search

Notification

Agent Runtime

Reasoning

Automation

Analytics

Audit

---

Future Services

Trading

ERP

Marketplace

Civilization Runtime

Organization Runtime

Simulation Engine

Physical Robot Runtime

---

# CHAPTER 8

# DATABASE ARCHITECTURE

Relational Database

PostgreSQL

Stores

Users

Projects

Chats

Tasks

Organizations

Settings

Agents

Permissions

Documents

Knowledge Metadata

Memory Metadata

Audit

Analytics

---

Cache

Redis

Stores

Sessions

Streaming

Queues

Temporary Context

Rate Limits

Agent State

Realtime Data

---

Vector Database

Qdrant

Stores

Embeddings

Knowledge

Memory

Documents

Research

Code

Images

---

Object Storage

Cloudflare R2

Stores

PDFs

Images

Audio

Video

Attachments

Models

Exports

Backups

---

# CHAPTER 9

# MEMORY ARCHITECTURE

Services

Memory Extraction

Memory Ranking

Memory Linking

Memory Retrieval

Memory Evolution

Memory Compression

Memory Verification

Memory Analytics

Memory Visualization

Memory Graph

Memory Timeline

Memory Search

---

# CHAPTER 10

# KNOWLEDGE ARCHITECTURE

Pipeline

Extraction

Normalization

Entity Detection

Relationship Discovery

Knowledge Linking

Confidence Scoring

Evidence Tracking

Knowledge Evolution

Inference

Visualization

---

# CHAPTER 11

# AGENT RUNTIME

Agent Registry

Agent Scheduler

Task Queue

Execution Engine

Shared Memory

Shared Knowledge

Delegation

Retry

Observability

Sandbox

Agent Communication

Agent Reflection

---

Future

Self-improving agents

Agent mentoring

Agent specialization

Agent societies

---

# CHAPTER 12

# AI RUNTIME

Supported Providers

OpenAI

Anthropic

Google

DeepSeek

OpenRouter

Ollama

LM Studio

Future providers

---

Capabilities

Streaming

Tool calling

Structured outputs

Vision

Speech

Reasoning

Embeddings

Fallback routing

Cost optimization

Latency optimization

Model selection

---

# CHAPTER 13

# SEARCH ARCHITECTURE

Keyword Search

Semantic Search

Hybrid Search

Graph Search

Temporal Search

Conversation Search

Document Search

Memory Search

Knowledge Search

Project Search

Agent Search

---

# CHAPTER 14

# DOCUMENT PIPELINE

Upload

Virus Scan

OCR

Parsing

Cleaning

Chunking

Embedding

Indexing

Knowledge Extraction

Relationship Extraction

Storage

Search

Versioning

Archive

---

# CHAPTER 15

# EVENT SYSTEM

Every subsystem publishes events.

Examples

UserCreated

WorkspaceCreated

ConversationStarted

ConversationSummarized

MemoryCreated

MemoryUpdated

KnowledgeLinked

DocumentIndexed

AgentStarted

AgentCompleted

PlannerExecuted

ResearchFinished

TaskCompleted

NotificationSent

Every event becomes observable.

---

# CHAPTER 16

# SECURITY ARCHITECTURE

Authentication

Authorization

RBAC

ABAC (future)

Encryption at rest

Encryption in transit

API Keys

OAuth

Audit logs

Secrets management

Rate limiting

Input validation

Malware scanning

Dependency scanning

Security monitoring

Threat detection

Backup verification

Disaster recovery

---

# CHAPTER 17

# OBSERVABILITY

Metrics

Tracing

Logging

Profiling

Health checks

Alerts

Cost tracking

Model usage

Latency

Failure rates

Agent success

Memory retrieval quality

Knowledge retrieval quality

User satisfaction

---

# CHAPTER 18

# AUTOMATION ENGINE

Triggers

Schedules

Webhooks

Conditions

Actions

Agent execution

Notifications

Workflow templates

Automation marketplace

Future no-code builder

---

# CHAPTER 19

# DEPLOYMENT

Development

Docker Compose

Staging

Production

Self-hosted

Cloud

Hybrid

Kubernetes

High Availability

Horizontal Scaling

Multi-region

Automatic Failover

---

# CHAPTER 20

# FUTURE EVOLUTION

The architecture must support future systems without redesign.

Future layers include

Trade Titans Ecosystem

Education Platform

Enterprise ERP

Healthcare Platform

Marketplace

Agent Economy

Agent Governments

Agent Civilizations

Autonomous Companies

Physical Companion Robot

Spatial Computing

Mixed Reality

Global Knowledge Network

Research Network

Planetary Intelligence Layer

Every future capability should plug into this architecture instead of replacing it.

---

# FINAL ENGINEERING LAW

The architecture is not successful because it is complex.

It is successful because it allows complexity to emerge without collapsing.

NÅNCY should be capable of growing from a single-user desktop application into a globally distributed sovereign intelligence platform without abandoning its architectural principles.

That is the standard every engineering decision must meet.

---

## END OF BOOK III — ENGINEERING ARCHITECTURE BIBLE

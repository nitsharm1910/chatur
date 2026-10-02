---
id: ADR-0009
title: v1 targets are Claude Code and GitHub Copilot
status: Accepted
date: 2026-10-02
deciders: Nitin
phase: requirements
tags: [scope, assistants]
---

# ADR-0009: v1 targets — Claude Code and GitHub Copilot

## Context
Building full adapters for every assistant up front spreads effort thin.

## Decision
v1 provides full support (instructions, agents, prompts/commands, skills, **enforcing hooks**)
for **Claude Code** (reference adapter) and **GitHub Copilot** (CLI + cloud agent via
`.github/hooks/*.json`, version 1 schema). Codex, Gemini CLI, and Cursor get instructions,
agents, and skills via APM, and are governed by the git/CI backstop (ADR-0005) until their
adapters land in v1.x.

## Consequences
- Copilot cloud agent hooks run bash only, so hook commands must not rely on PowerShell there.
- Copilot `preToolUse` fails closed on crash, so the adapter must never crash. It wraps everything and emits an explicit decision.

# Python Service Libs

Shared Python libraries for IoT Hub microservices, including reusable infrastructure and service utilities.

## Purpose

The `python-service-libs` repository contains reusable Python packages that can be shared across multiple IoT Hub microservices.

Its goal is to reduce duplication of technical infrastructure code while keeping service-specific business logic inside individual microservice repositories.

## Responsibilities

- provide reusable Python packages for shared technical concerns
- support consistent integration patterns across Python-based microservices
- centralize common infrastructure abstractions
- define reusable utilities for messaging, observability, audit publishing, and similar cross-service needs
- support versioned distribution of shared Python packages

## Package areas

This repository contains such packages:

- `kafka-kit` — reusable Kafka producer and consumer abstractions
- `observability-kit` — metrics, logging, tracing, and runtime observability helpers
- `audit-kit` — audit event models and publishing helpers
- `serializer-kit` — service-agnostic serializer base classes
- `test-kit` — reusable testing utilities for Python services

## Design principles

Only shared technical building blocks should be placed here.

This repository should **not** contain:
- service-specific business logic
- domain models owned by individual microservices
- shared database models
- code that creates tight coupling between service boundaries

## Usage

Microservices are expected to consume these libraries as versioned Python dependencies rather than copying shared code into service repositories.

# Small Models, Big Impact: Why Your Next Production System Doesn’t Need a GPT

## **Elevator Pitch**

What if intelligence wasn’t centralized in one giant model? Discover how small, local models are quietly orchestrated to handle most of the work inside modern AI systems—and why this hidden layer is becoming the new architecture.

## **Description**

Most modern AI systems are built around a single assumption: that **“intelligence” lives behind a remote API**. A request goes in, a large model responds, and the application wraps around it. This works well for prototypes but behaves very differently under real-world load, cost constraints, and failure modes.

In this talk, we’ll examine how production AI systems are quietly evolving toward something else: an **intelligence layer** composed of multiple models, each responsible for a different part of the request lifecycle. Rather than treating language models as monolithic endpoints, these systems decompose work into **classification, routing, extraction, verification, and generation** and assign each step to a model chosen for its latency, reliability, and cost profile.

We’ll look at what makes this shift possible today: **compact language models that can run locally**, **quantization techniques that change memory and deployment boundaries**, and **modern inference runtimes** that turn models into infrastructure components rather than cloud services.

This session is not about picking **“the best model.”**

It is about understanding how **model size becomes an architectural decision** and how that changes the way AI systems are designed.

## **Notes**

This talk draws on long-term experience building and operating AI systems where models must function under real-world constraints of latency, cost, reliability, and deployment complexity.

**What the session will include**

- Architectural perspectives on how modern AI systems are evolving from single-model APIs into layered, multi-model pipelines.
- Conceptual and visual breakdowns of how requests flow through classification, routing, validation, and generation stages.
- A concise demonstration that illustrates how multiple models collaborate within a single AI workflow.
- Observations from real systems on how model choice affects system behavior, performance, and operational cost.

**Demo & technical requirements**

The session includes a compact, self-contained demonstration designed to support the architectural discussion and make the concepts concrete, without introducing setup or infrastructure overhead.

**Goal for reviewers**

This talk is not about comparing models or showcasing benchmarks. It presents a design pattern for treating language models as composable system components, giving Python developers a framework for building AI systems that are easier to scale, reason about, and operate in practice.

## Speaker Bio

**Gokulavasan Murali** *Head of Engineering, Emma Robots Inc. | Ex-Plena, Flytta, Accenture*

Gokul is a seasoned Product Engineer and Architect with over a decade of experience defining the frontier of autonomous systems. A specialist in the convergence of Computer Vision and Agentic AI, Gokul currently serves as the **Head of Engineering at Emma Robots**, where he is pioneering **Vision-First RPA** and **Computer Using Agent (CUA)** systems that perceive and interact with software interfaces with the visual nuance of a human operator.

Previously, as Head of Engineering at Plena Inc. (acquired by Chief), Gokul architected AI Sales Agents that revolutionised browser-based workflow automation. His deep technical roots trace back to the mobile edge, where he co-founded Flytta and deployed some of the world’s first mobile-native Deep Learning models for logistics and driver safety. His career began in the rigorous world of embodied robotics, where he led teams to design semi-autonomous navigation systems on embedded supercomputers and build autonomous underwater vehicles.

Gokul is a long-time member of the Python community and has previously been part of organising **PyCon India**.
# Tender-matic initial specification

## Problem
Whenever there is a new public tender, the BID team is hurried to generate a good-quality response as fast as possible due to the limited time window given by the customer, so there are the following needs:

> Fully read and understand the new tender
> Identify our solution's capabilities
> Match what tenders asks vs what the solution offers out of the box
> Identify the gaps between the solution and what tender asks
> Generate questions about technical & operational aspects that are not ovbious or ambiguous in the tender to take to the clarification meetings
> Generate an initial technical proposal for the tender that ensures the compliance of the requsites or either outline what is needed to develop from scratch or integrate
> Also, in the generated proposal, outline major risks given the information contained in the tender and what we know from the company and the solution

## Constraints & requisites

> Proposals already generated and delivered in the past shall be the basis for the new proposal, no single thing never proposed in the history can be assumed as a company or solution capability
> There must be a company-local mechanism to query for historical documentation about past tenders
> Company scoped information shall never be shared outside the company
> All the knowledge and know-how about the business must never be disclosed or shared with third parties, everything must remain local for the company

## Description of the solution

Expected output is an AI Agentic solution with: 
> Usage of MCP to ingest the historical documents and/or RAG to build a knwoledge base for this purpose
> Selection and implementation of the architecture that best suits this requirement (single agent, prompt chaining, multi-agent, and so fort), the main tradeoffs and architecture decisions shall be well documented and sustented (what, why and how?)
> Selection of the tech stack that best suits this requirement (Calude is a must, but for mcp, RAG, agents, describe the used tools, libraries and why) 
> Documentation about the ingestion of both pre-existing generated proposals and new tenders received
> As it's been said, to look for the best options in terms of local information usage, token otimization, ease of use, since we intend to deliver a tool that can be used by a non-technical team
> Every decision well foundamented and documented

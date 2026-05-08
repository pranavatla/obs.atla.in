# AtlaOps Architecture

AtlaOps is designed as a portfolio-grade cloud operations demo that mirrors production architecture patterns.

## Reference Topology

- Route53 for DNS
- CloudFront for global edge caching and TLS termination
- S3 for static dashboard assets
- API Gateway for backend routing
- Lambda for stateless AI orchestration and ops APIs
- Vector store for retrieval context (project docs, postmortems, runbooks)
- Managed LLM API for inference
- CloudWatch for metrics, alerts, and incident signals

## Key Design Decisions

- Keep frontend and API independently deployable while exposing a single user experience.
- Separate synthetic demo telemetry from user chat traffic.
- Make incident state explicit and queryable so AI responses can include current system conditions.
- Design for no-GPU inference by relying on managed model APIs.

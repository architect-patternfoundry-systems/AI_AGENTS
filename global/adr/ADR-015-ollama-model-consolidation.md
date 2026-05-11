# ADR-015: Ollama Model Consolidation Opportunity

## Status
Proposed

## Context
The workspace currently runs two separate Ollama models for different services:

- **llama3** (4.7GB): Used by Storyloom for narrative generation
  - Tags: `llama3:latest`, `llama3:8b` (same model, different tags)
  - Services: Storyloom API, Storyloom AI service
  - Configuration: `OLLAMA_STORY_MODEL=llama3:8b`

- **gemma2:9b** (5.4GB): Used by CTS (Content Transformation Services)
  - Services: CTS Semantic Engine (Rust), CTS Stoic Translator, CTS Intelligence Service
  - Last modified: January 2026 (older than llama3)

**Total Ollama model storage**: ~10GB

Additionally, the workspace has Qwen2.5 models already cached via HuggingFace:
- `Qwen/Qwen2.5-3B-Instruct` (999.6MB + 2.1GB blobs)
- `Qwen/Qwen2.5-0.5B-Instruct` (available)

## Decision
**PENDING**: Evaluate model consolidation when either Storyloom or CTS is next updated.

### Proposed Evaluation Criteria
When updating either service, evaluate whether a single Qwen2.5 variant could serve both use cases:

1. **Performance benchmarks**: Compare Qwen2.5-3B-Instruct against current models for:
   - Narrative generation quality (Storyloom use case)
   - Semantic analysis accuracy (CTS use case)
   - JSON structured generation capability (both use cases)

2. **Resource efficiency**: 
   - Qwen2.5-3B-Instruct: ~3GB total (smaller than llama3 4.7GB + gemma2 5.4GB = 10GB)
   - Potential savings: ~7GB

3. **Capability coverage**:
   - Instruction following (both services require)
   - JSON mode support (CTS requires for structured output)
   - Context window requirements
   - Multilingual support (if needed)

4. **Migration effort**:
   - Configuration changes required
   - API compatibility
   - Performance testing requirements

### Implementation Plan (If Approved)
1. **Phase 1**: Benchmark Qwen2.5-3B-Instruct against current models
2. **Phase 2**: Update Storyloom to use Qwen2.5-3B-Instruct (if benchmarks pass)
3. **Phase 3**: Update CTS services to use Qwen2.5-3B-Instruct (if benchmarks pass)
4. **Phase 4**: Remove unused models from Ollama
5. **Phase 5**: Monitor performance and quality metrics

### Rollback Plan
- Keep current models available during transition period
- Revert configuration if quality/performance degrades
- Document performance baseline for comparison

## Consequences
**Positive**:
- Potential 7GB storage savings
- Simplified model management (single model instead of two)
- Reduced memory footprint for Ollama service
- Leverage already-cached HuggingFace models

**Negative**:
- Migration effort required
- Potential performance regression risk
- Need for comprehensive testing
- Possible quality degradation in niche use cases

**Neutral**:
- Qwen2.5 is newer model family (less battle-tested in production)
- Different ecosystem (HuggingFace vs Ollama-native)

## Alternatives Considered
1. **Status quo**: Keep both models (current state)
   - Pro: No risk, working solution
   - Con: 10GB storage usage, two models to maintain

2. **Consolidate to llama3 only**: Use llama3 for both services
   - Pro: Single model, already in Ollama
   - Con: Larger than Qwen2.5 (4.7GB vs 3GB), may not suit CTS semantic analysis

3. **Consolidate to gemma2 only**: Use gemma2 for both services
   - Pro: Single model
   - Con: Older model (Jan 2026), larger than Qwen2.5 (5.4GB vs 3GB)

4. **Model serving architecture change**: Move to external model API (OpenAI, Anthropic, etc.)
   - Pro: No local storage needed
   - Con: External dependency, cost, latency

## References
- Current Ollama models: `llama3:latest` (4.7GB), `gemma2:9b` (5.4GB)
- Cached HuggingFace models: `Qwen/Qwen2.5-3B-Instruct` (~3GB total)
- Storyloom configuration: `storyloom/.env.example`, `storyloom/deploy-apps.yaml`
- CTS services: `cts/semantic-engine-rust/src/ollama.rs`, `cts/src/ingestion/*.py`

## Notes
- User has already cleaned up ~36GB of old Stable Diffusion models from `/home/cortex/ai_lab/stable-diffusion-webui/models/`
- Disk pressure issue on cortex node has been resolved
- This ADR should be revisited during next major update to either Storyloom or CTS
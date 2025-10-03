# Performance & Efficiency Improvements

_Updated: October 2025_

This release focuses on making MCP interactions faster, cheaper in tokens, and easier to reason about. Below is a detailed breakdown of the changes, why they matter, and the challenges tackled during implementation.

## 1. Token-conscious page summaries
- **What changed:** Added `BrowserService.preprocess_page_content` and the `resource://page_markdown/{session_id}` resource. The helper uses `readability-lxml` to isolate readable markup and `html2text` to render a compact markdown summary.
- **Impact:** Large DOMs now shrink dramatically before reaching the LLM. The response includes `token_savings` metrics so agents can decide whether to reuse cached summaries.
- **Challenge:** Ensuring readability extraction wouldnt throw on malformed pages. We wrapped the readability call in a guard that falls back to raw HTML and still reports savings.

## 2. Cache-aware element inspection
- **What changed:** `describe_elements` accepts `use_cache` / `force_refresh` parameters and stores payloads keyed by page hash, selector, and attribute bundle.
- **Impact:** Repeated calls during multi-step reasoning dont re-query the DOM, saving Playwright RPC chatter and token budget.
- **Challenge:** Avoiding cache pollution when HTML previews are included. We disable caching automatically when `include_html_preview` is true, keeping memory use predictable.

## 3. Smarter click-target ranking
- **What changed:** `find_click_targets` now computes fuzzy similarity with `SequenceMatcher`, adds viewport and role bonuses, and caches ranked lists per query signature.
- **Impact:** Results return in fewer tokens with clearer confidence scores, and subsequent lookups for the same label rehydrate instantly from cache.
- **Challenge:** Matching vectors needed debouncing to prevent shallow matches. We gate fuzzy hits behind a similarity threshold and require substring presence when running in fuzzy mode.

## 4. Condensed accessibility snapshots
- **What changed:** `get_accessibility_tree` performs a breadth-first traversal with scoring (focus, role match, depth) and produces summaries/child counts, caching snapshots across identical filter sets.
- **Impact:** Accessibility diagnostics are slimmer and deterministic, keeping responses manageable for LLMs while highlighting the most actionable nodes first.
- **Challenge:** Traversing large trees risked runaway memory. Switching to BFS with `deque` honors `max_nodes` limits tightly and avoids recursion depth issues.

## 5. Shared session cache plumbing
- **What changed:** `BrowserService` now owns a `SessionManager` reference (attached in both FastAPI and FastMCP lifecycles). The manager invalidates caches when sessions close.
- **Impact:** Cached diagnostics can be reused across tools (`inspect_elements`, `find_click_targets`, accessibility snapshots, markdown preprocessing) with automatic eviction when sessions end.
- **Challenge:** Preventing stale hashes after navigation. We hash page content before reads and store it with cache entries so any DOM change invalidates the payload automatically.

## 6. Documentation & tooling updates
- **What changed:** README, tool reference, and tool signatures document the new parameters and resource. Tools expose `use_cache`/`force_refresh` toggles for explicit cache control.
- **Impact:** Operators understand when cache hits occur, how to force refreshes, and where to fetch markdown summaries.
- **Challenge:** Keeping MCP registration happy when adding optional parameters to resources. We restricted URI templates to declared parameters and pass other options via query/body when needed.

If you spot regressions or have ideas for further tuning (e.g., cache eviction policies, adaptive scoring weights), drop an issue in the tracker!

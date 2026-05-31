# ADR-015: Resource Resolution Priority Framework

## Status
Accepted (Enhanced)

## Canonical Implementation
- Base class: `application/apps/toneroot/web/backend/sidecar_main.py` (ResourceLocator class)
- Reference implementation: `ConfigLocator` in `sidecar_main.py`
- Test suite: `application/apps/toneroot/web/backend/test_config_resolution.py`
- Build integration: `application/apps/toneroot/web/frontend/src-tauri/build-sidecar.py`

**If these paths are wrong, this ADR is stale — update before citing.**

## Context
We encountered a **Resource Resolution Priority Inversion** bug where the PyInstaller temporary bundle directory (`sys._MEIPASS`) was taking precedence over the user's persistent config directory (`~/.local/share/com.toneroot.nexus/config.json`). This caused the application to ignore user configuration and always load bundled defaults, making the setup wizard appear repeatedly even after configuration.

This bug class is particularly insidious because:
- It manifests only in packaged/frozen builds, not during development
- It causes silent correctness failures (no crash, wrong data loaded)
- It frequently survives code review because logic "looks correct" in isolation
- It violates the Principle of Least Surprise for user expectations

## Decision
We adopt a **Resource Resolution Priority Framework** that treats lookup chains as first-class invariants with explicit test coverage, rather than emergent consequences of code order.

### Resource Locator Pattern
All resource resolution MUST use the `ResourceLocator` base class with explicit tier definitions:

```python
class ResourceLocator:
    """Base class for tiered resource resolution with priority inversion prevention."""
    
    TIERS = []  # Subclasses declare their chain with conditions and resolvers
    
    def locate(self) -> str:
        for i, tier in enumerate(self.TIERS, 1):
            if tier["condition"]():  # Eligibility check is first-class
                result = tier["resolver"](self)
                if result:
                    logger.info(f"[Resource] Tier {i} ({tier['name']}): resolved → {result}")
                    return result
```

### Tier Structure Requirements
Each tier MUST include:
- `name`: Human-readable identifier for logging
- `condition`: Lambda function returning bool (eligibility is explicit)
- `resolver`: Lambda function returning path or None

This makes eligibility conditions **first-class parts of tier definitions**, preventing the original bug where `sys.frozen` checks were scattered in resolver bodies.

### Failure Contract
All ResourceLocator subclasses MUST support two invocation patterns:

**Lenient (default):** `locate()` returns `str | None`
- Used when fallback behavior is acceptable
- Caller must guard against None: `if path: load(path)`
- Appropriate for config files with defaults

**Strict:** `locate_or_raise()` returns `str` (never None)
- Used when resource is required for operation
- Raises exception on total miss: `locator.locate_or_raise(CustomError, "Critical asset missing")`
- Appropriate for theme files, plugins, required assets

This dual contract allows callers to opt into strict vs lenient behavior explicitly at the call site, rather than each locator inventing its own error handling.

### Implementation Requirements
1. **Use ResourceLocator base class** - Inherit for automatic logging and priority enforcement
2. **Declare TIERS with conditions** - Eligibility is explicit, not implicit in code order
3. **Rate limit warnings** - Use `_warn_once()` to prevent log flooding on restarts
4. **Test with frozen context fixture** - Realistic simulation of `sys._MEIPASS` with actual files
5. **Validate loaded content** - Assert actual file contents, not just paths
6. **Cross-platform path resolution** - Use `platformdirs` for XDG compliance

### Detection Mechanisms
- **Runtime logging**: Each tier logs resolution/miss/skip with tier identifier
- **Rate-limited warnings**: Bundle fallback warnings emit once per process
- **Content validation**: Tests verify actual file contents, not just paths
- **Frozen context fixture**: Realistic simulation of packaged environment
- **CI validation**: Automated testing of frozen binary config resolution

## Consequences
### Positive
- **Prevents silent config loading errors** - Priority inversions detected at runtime
- **Cross-platform compliance** - Uses `platformdirs` for XDG Base Directory Specification
- **Testable invariants** - Priority chain can be asserted against in automated tests
- **Debuggable resolution** - Clear logging shows exactly which tier was selected and why
- **Reusable pattern** - ResourceLocator base class applies to plugins, assets, data directories
- **No log flooding** - Rate-limited warnings prevent spam on frequent restarts
- **Explicit eligibility** - Conditions are first-class, preventing scattered guard logic
- **Consistent failure contracts** - Dual lenient/strict pattern across all locators

### Negative
- **Additional test maintenance** - Requires maintaining test suite for each resolution tier
- **Runtime logging overhead** - Minimal performance impact from logging each tier
- **Dependency on platformdirs** - Adds a dependency for cross-platform path resolution
- **Learning curve** - Developers must understand ResourceLocator pattern

## Implementation
See `sidecar_main.py` for the canonical implementation:
- Base class: `ResourceLocator` with tier-by-tier resolution logic
- Config implementation: `ConfigLocator` extends ResourceLocator
- Tier definitions: ConfigLocator.TIERS with explicit conditions and resolvers
- Test suite: `test_config_resolution.py` with frozen context fixture
- Build integration: Added `platformdirs` to PyInstaller hidden imports

## Evolution
### V1 (Initial)
- Simple priority list constant
- Implicit code order for resolution
- Basic logging per tier

### V2 (Enhanced)
- ResourceLocator base class for reusability
- Explicit tier conditions (not implicit in code order)
- Rate-limited warnings via `_warn_once()`
- Frozen context fixture for realistic testing
- Content validation (not just path validation)
- Cross-platform platformdirs integration

### V3 (Complete - Current)
- Dual failure contract: `locate()` (lenient) + `locate_or_raise()` (strict)
- Consistent error handling across all locators
- Explicit opt-in to strict vs lenient behavior at call site
- Test coverage for both invocation patterns

## References
- [PyInstaller Runtime Information](https://pyinstaller.org/en/stable/runtime-information.html)
- [PyInstaller Issue #7127](https://github.com/pyinstaller/pyinstaller/issues/7127)
- [XDG Base Directory Specification](https://specifications.freedesktop.org/basedir-spec/basedir-spec-latest.html)
- [platformdirs Documentation](https://platformdirs.readthedocs.io/)

## Examples
### Correct Implementation (ResourceLocator Pattern)
```python
class ConfigLocator(ResourceLocator):
    def __init__(self):
        super().__init__("Config Resolution")
    
    TIERS = [
        {
            "name": "env_override",
            "condition": lambda: bool(os.environ.get("TONEROOT_CONFIG")),
            "resolver": lambda self: self._resolve_env_override(),
        },
        {
            "name": "user_config_dir",
            "condition": lambda: True,  # Always eligible
            "resolver": lambda self: self._resolve_user_config_dir(),
        },
        {
            "name": "bundle_dir",
            "condition": lambda: getattr(sys, "frozen", False),  # Only in frozen builds
            "resolver": lambda self: self._resolve_bundle_dir(),
        },
    ]
    
    def _resolve_bundle_dir(self) -> str | None:
        if getattr(sys, "frozen", False):
            bundle_path = os.path.join(sys._MEIPASS, "config.json")
            if os.path.isfile(bundle_path):
                self._warn_once("bundle_dir", f"Using bundled config: {bundle_path}")
                return os.path.normpath(bundle_path)
        return None

# Usage examples
locator = ConfigLocator()

# Lenient: returns None if no config found (caller handles fallback)
config_path = locator.locate()
if config_path:
    load_config(config_path)
else:
    use_defaults()

# Strict: raises exception if no config found (resource is required)
try:
    config_path = locator.locate_or_raise(FileNotFoundError, "Config required for startup")
    load_config(config_path)
except FileNotFoundError as e:
    log_and_exit(e)
```

### Incorrect Implementation (Original Bug)
```python
# WRONG: Bundle takes priority over user config due to code order
candidates = []
if getattr(sys, "frozen", False):
    candidates.append(os.path.join(sys._MEIPASS, "config.json"))  # BUG: First!
candidates.append(os.path.expanduser("~/.local/share/com.example.app/config.json"))
for path in candidates:
    if os.path.isfile(path):
        return path  # Returns bundle even if user config exists!
```

## Migration Guide
When adding new resource resolution (config files, data directories, plugin paths):
1. Create subclass of ResourceLocator
2. Define TIERS with explicit conditions and resolvers
3. Implement resolver methods with _warn_once() for warnings
4. Add frozen context fixture tests with content validation
5. Validate platformdirs integration in frozen context
6. Document the resolution order in class docstring

## How to Add a New Locator

Copy this mechanical template and fill in the blanks:

```python
from sidecar_main import ResourceLocator

class NewResourceLocator(ResourceLocator):
    """
    Resolves [resource name] following the explicit priority chain.
    
    Priority Chain (highest to lowest):
      1. [Tier 1 description]
      2. [Tier 2 description]
      3. [Tier 3 description]
    """
    
    def __init__(self):
        super().__init__("[Resource Name] Resolution")
    
    # Implement resolver methods (one per tier)
    def _resolve_tier_1(self) -> str | None:
        # Your resolution logic here
        # Use self._warn_once() for warnings that shouldn't spam logs
        return path_or_none
    
    # Declare the tier chain with conditions and resolvers
    TIERS = [
        {
            "name": "tier_1_name",
            "condition": lambda: [eligibility condition],
            "resolver": lambda self: self._resolve_tier_1(),
        },
        {
            "name": "tier_2_name",
            "condition": lambda: [eligibility condition],
            "resolver": lambda self: self._resolve_tier_2(),
        },
    ]
```

**Usage convention:**
- Required resources: Always use `locate_or_raise()`
- Optional resources: Always use `locate()` with None guard

```python
# Required resource (theme, critical plugin)
locator = NewResourceLocator()
resource_path = locator.locate_or_raise(FileNotFoundError, "Critical resource missing")
load_resource(resource_path)

# Optional resource (optional plugin, fallback asset)
locator = NewResourceLocator()
resource_path = locator.locate()
if resource_path:
    load_resource(resource_path)
else:
    use_fallback()
```

## How to Add a New Tier to an Existing Locator

When adding a new tier to an existing locator, you MUST include all three tier components:

```python
# CORRECT: Complete tier definition
{
    "name": "new_tier_name",              # Human-readable identifier
    "condition": lambda: [boolean expr],  # Eligibility check (REQUIRED)
    "resolver": lambda self: self._resolve_new_tier(),  # Resolution logic
}
```

**CRITICAL:** The `condition` lambda is REQUIRED. Adding a tier without a condition is the exact footgun this framework was built to prevent — it causes priority inversion when the new tier should only be eligible in specific contexts (e.g., frozen builds only, development mode only, etc.).

**Common condition patterns:**
```python
# Always eligible
"condition": lambda: True

# Only in frozen/packaged builds
"condition": lambda: getattr(sys, "frozen", False)

# Only in development
"condition": lambda: not getattr(sys, "frozen", False)

# Only when environment variable is set
"condition": lambda: bool(os.environ.get("MY_APP_VAR"))

# Only when specific feature flag is enabled
"condition": lambda: os.environ.get("FEATURE_X") == "enabled"
```

## Conflict Resolution Semantics

The current ResourceLocator implementation uses **first-wins semantics**: the first tier in the priority chain that returns a valid path wins. This is appropriate for:

- ✅ Config files (first valid config wins)
- ✅ Theme assets (first valid theme wins)
- ✅ Data directories (first valid directory wins)

**Future consideration:** For `PluginLocator` or scenarios where merge/override semantics are needed (e.g., user plugins should override bundled plugins with the same name), a different base class pattern would be required. This is outside the current V3 scope but should be evaluated if conflict resolution becomes a requirement.

## Extending the Pattern
The ResourceLocator base class can be used for:
- **ConfigLocator**: Configuration file resolution ✅ (implemented)
- **PluginLocator**: Plugin directory resolution (ready to implement)
- **AssetLocator**: Theme/asset file resolution (ready to implement)
- **DataLocator**: Data directory resolution (ready to implement)

Each subclass simply declares its TIERS - logging, precedence, and testability come for free from the base class.

## Carry-Forward Conventions

**Code Review Checklist:**
When reviewing code that uses ResourceLocator subclasses, verify:

1. **Required resources use `locate_or_raise()`**
   - Theme files, critical plugins, required assets
   - Should raise explicit exception if missing
   - Example: `theme_path = ThemeLocator().locate_or_raise(FileNotFoundError, "Theme required for UI")`

2. **Optional resources use `locate()` with None guard**
   - Optional plugins, fallback assets, non-critical configs
   - Caller must handle None gracefully
   - Example: `plugin_path = PluginLocator().locate(); if plugin_path: load_plugin(plugin_path)`

3. **All tier definitions include `condition` lambda**
   - Never add a tier without a condition
   - Prevents priority inversion bugs in new contexts
   - See "How to Add a New Tier" section for patterns

4. **Warnings use `_warn_once()` for rate limiting**
   - Prevents log flooding on restarts
   - Diagnostic warnings, not per-request metrics

These conventions make the intent auditable during code review without requiring call graph analysis.

## Related Patterns
- **Configuration Precedence**: Environment > User > System > Default
- **Plugin Loading**: User plugins > Bundled plugins > Core plugins  
- **Data Directory Resolution**: XDG paths > Legacy paths > Fallback
- **Asset Loading**: User overrides > Theme assets > Default assets
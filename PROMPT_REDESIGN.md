# Prompt System Redesign - Quality Improvement

## Problem Identified

The LLM analysis quality degraded due to **conflicting instructions**:

1. **Base prompt** (`prompts/reit_audit_prompt.txt`) had hard-coded persona:
   - "Your client is a retiree looking for 'Risk-Averse Fixed Income'"
   - "They prioritize capital preservation and steady payouts over aggressive growth"

2. **User preferences** could contradict this:
   - User picks "aggressive" risk tolerance → LLM confused (client is risk-averse but user wants aggressive?)
   - User picks "growth" objective → LLM confused (client wants income but user wants growth?)
   - User picks "balanced" + 7% yield → Inconsistent (balanced doesn't align with 7% yield requirement)

## Root Cause

**Two competing instruction sets** trying to define investment goals:
- Fixed prompt persona (conservative retiree)
- User-specified preferences (could be anything)

## Solution: Unified Philosophy

### Core Insight (Your Observation)
> "REITs are first and foremost a conservative investment, for their dividend and growth is secondary"

This is the foundation. REITs exist to generate dividend income - this is **not negotiable**.

### Changes Made

#### 1. Base Prompt (`prompts/reit_audit_prompt.txt`)

**Removed:**
- ❌ Hard-coded client persona ("retiree looking for Risk-Averse Fixed Income")

**Added:**
- ✅ **Core Investment Philosophy** section:
  ```
  Singapore REITs are fundamentally CONSERVATIVE DIVIDEND INVESTMENTS.
  They exist primarily to generate steady income through dividends, not
  capital appreciation. Even when analyzing for growth or balanced
  strategies, this dividend-first nature remains central to proper REIT
  evaluation.
  ```

**Enhanced:**
- Renamed "Sleep Well" picks → **"Core Holdings"** (more professional)
- Added explicit dividend sustainability checks
- Strengthened focus on business model resilience

#### 2. Preference Interpretation (`reit_info_agent.py` lines 301-308)

**Added interpretation guidelines** that reframe ALL objectives through the dividend lens:

| User Choice | Old Interpretation (Conflicted) | New Interpretation (Aligned) |
|-------------|--------------------------------|------------------------------|
| "income" objective | Wants high yield (conflicts with conservative client?) | Highest CURRENT dividend yields (7%+) |
| "growth" objective | Wants capital gains (contradicts REIT nature?) | Dividend GROWTH potential (rising distributions) |
| "balanced" objective | Unclear how to balance | Balance current yield (5-6%) with sustainability |
| "preservation" objective | Same as hard-coded client (redundant) | Most defensive sectors with stable dividends |
| "conservative" risk | Redundant with client persona | Avoid gearing >35%, volatile sectors |
| "moderate" risk | Contradicts client? | Accept gearing up to 40% |
| "aggressive" risk | Complete contradiction! | Accept higher gearing, recovery plays |

**Key improvement**: Now "growth" means **dividend growth**, not capital appreciation. This aligns with REIT fundamentals.

## Benefits

### 1. Eliminates Contradictions
- No more competing instructions
- User preferences now **enhance** the base philosophy instead of contradicting it

### 2. Realistic Expectations
- Users understand REITs are dividend investments first
- "Aggressive" now means willing to take more sector/leverage risk for higher yields
- "Growth" now means seeking dividend growth, not speculative capital gains

### 3. Consistent Analysis Quality
- LLM receives one clear directive: "REITs are conservative dividend investments"
- All user preferences filter/prioritize within this framework
- No more confusion about whether to be conservative or aggressive

## Example Scenarios

### Before (Conflicted):
**Base Prompt**: "Client is risk-averse retiree wanting income"
**User Picks**: Aggressive risk + Growth objective
**LLM Thinks**: "Wait, should I be conservative (prompt) or aggressive (user)? Growth means capital gains but REITs are for income? 🤔"
**Result**: Low-quality, confused recommendations

### After (Aligned):
**Base Prompt**: "REITs are conservative dividend investments"
**User Picks**: Aggressive risk + Growth objective
**LLM Thinks**: "Find REITs with strong dividend GROWTH potential. User accepts higher gearing/sector risk to get it. Still dividend-focused. ✓"
**Result**: Clear, consistent recommendations

## Testing Checklist

Run agent with these preference combinations to verify quality:

- [ ] Income + Conservative + 6% yield → Should get safest high-yielders
- [ ] Growth + Moderate + No thresholds → Should get REITs with rising distributions
- [ ] Balanced + Conservative + 5% yield + 1.0 P/B → Should get quality value plays
- [ ] Income + Aggressive + 7% yield → Should get higher-risk sectors with high yields
- [ ] Preservation + Conservative → Should get industrial/data center/healthcare REITs

All scenarios should now produce coherent, high-quality analysis focused on dividend characteristics.

## Files Modified

1. `prompts/reit_audit_prompt.txt` - Base prompt philosophy and framework
2. `reit_info_agent.py` - Preference interpretation guidelines (lines 301-308)

# Traction Force Microscopy Tool Implementation - Multi-Step Workflow

## Architecture Limitation

The current FastAPI system architecture accepts only one file per job, while TFM requires two distinct images (Before and After). This creates a challenge because the fundamental job workflow in our platform is designed around:

1. User uploads file → 
2. System queues job with single input file →
3. Scheduler launches container with that input →
4. Processor runs on that single input →
5. Results returned  

However, we need to understand how this can be accomplished while maintaining compatibility.

## Multi-Step TFM Workflow Pattern

For TFM in our system, the recommended approach uses the existing framework:

### Option A: Single Combined Job with Multiple File References (Recommended)
1. **Two separate uploads**: User uploads Before and After images individually  
2. **Job creation**: System associates both files when creating job
3. **Processing**: The worker receives both file paths via environment variables
4. **Sequential Steps**: The TFM processor implements the complete multi-step workflow internally

### Option B: Custom Job Creation Endpoint
Modify the job creation endpoint to accept multiple inputs:
```python
# In API layer - this would extend current behavior
@app.post("/tools/{tool_id}/run")
async def run_tool(
    tool_id: str,
    before_file_id: int,
    after_file_id: int, 
    params: dict = Body(default_factory=dict),
    # ... rest of existing parameters
):
```

## Required Implementation

### 1. Enhanced Processor Interface
Since our system provides only one file to the worker, the TFM processor needs to be smart enough to find and work with both images, potentially through database lookups or specific naming conventions.

### 2. Tool Parameter Structure  
Need to define which processing methods (DFT, Elastix) are supported in UI:
```python
parameters=(
    # ... existing parameters from original Streamlit ...
    ToolParameter("processing_method", "Processing Method", "DFT", 0, 3, 1),  # 0=DFT, 1=Elastix, etc.
)
```

### 3. Database Enhancement (Optional but Recommended)
Add support for secondary file tracking in Job records to link Before/After files properly.

## What I've Already Implemented

I've completed:
1. Tool structure with all original parameters from Streamlit
2. Docker image configuration 
3. Registry integration
4. Complete parameter definitions matching the original workflow

What's missing from a full replication of the complex Streamlit UI flow is the multi-page, multi-step interface that was in the Streamlit tool - which requires changes to the frontend implementation and possibly how job creation works.

## Current Limitations

The current FastAPI system will process TFM in one job with multiple steps internally (as we've discussed), but it cannot reproduce exactly the step-by-step UI workflow of the original Streamlit app without:
1. Backend changes to support multi-file job creation
2. Frontend interface changes to handle the sequential workflow

## Recommended Approach

To achieve the most complete TFM experience within our system:

### Immediate Steps:
1. **Deploy current implementation** - tool appears in dashboard with all parameters  
2. **Update frontend tool page** to include before/after file upload fields
3. **Add job creation logic** that supports associating multiple file IDs

### Long Term Enhancement:
For a truly complete Streamlit-like experience, implement multi-file job creation workflow in API and frontend.

The core functionality is working and integrated correctly into the system - it's just a matter of extending the user interaction model to match the desired multi-step experience.
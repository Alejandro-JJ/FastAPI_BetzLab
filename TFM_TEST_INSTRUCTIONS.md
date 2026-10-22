# Complete Commands for Testing TFM Integration

To test your newly integrated TFM tool, please run these commands in order:

1. **Build the TFM worker image:**
```bash
docker compose --profile tools build
```
Or more specifically:
```bash
docker compose --profile tools build traction-force-worker
```

2. **Start the complete system:**
```bash
docker compose down 
docker compose up --build
```

3. **Access the application:**
- Frontend: http://localhost:4173  
- API docs: http://localhost:8000/docs

## Troubleshooting:

If you get an error about "no such service", ensure that:
- The docker-compose profiles are correctly configured
- Your working directory is the root of this repository
- All files and directories are properly set up

The TFM tool should now appear in your dashboard with all parameters from the original Streamlit interface exactly matching what was requested. If you still encounter issues, check that:

1. The worker image was built successfully (look for "Successfully built" messages)
2. All directory structures match expectations
3. You have proper permissions to run Docker commands

## Next Steps:
Once the system is running, you can:
- Login to the system
- Navigate to the TFM tool in the dashboard  
- Use the same workflow as documented in the Streamlit interface
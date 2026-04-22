#!/bin/bash
# Test script for binding tag API endpoints
# Run with: bash test_binding_api.sh

ZKP_BACKEND_URL="http://localhost:5010"

echo "🧪 Testing Binding Tag API Endpoints"
echo ""

# Test 1: Generate proof without binding tag (backward compatible)
echo "Test 1: Generate proof without binding tag"
curl -X POST "$ZKP_BACKEND_URL/zkp/generate-value-commitment-with-blinding" \
  -H "Content-Type: application/json" \
  -d '{
    "value": 1000000,
    "blinding_hex": "0x4242424242424242424242424242424242424242424242424242424242424242"
  }' | jq '.'

echo ""
echo ""

# Test 2: Generate proof with binding tag
echo "Test 2: Generate proof with binding tag"
BINDING_TAG="0xb3d9660812695cf688a896d66e3349c1eb1e0ceb81307d2360f0f1ca3a3ad875"
curl -X POST "$ZKP_BACKEND_URL/zkp/generate-value-commitment-with-binding" \
  -H "Content-Type: application/json" \
  -d "{
    \"value\": 1000000,
    \"blinding_hex\": \"0x4242424242424242424242424242424242424242424242424242424242424242\",
    \"binding_tag_hex\": \"$BINDING_TAG\"
  }" | jq '.'

echo ""
echo "✅ API tests complete!"


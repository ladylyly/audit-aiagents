// Test script for binding tag API endpoints (Node.js)
// Run with: node test_binding_api.js

const http = require('http');

const ZKP_BACKEND_URL = process.env.ZKP_BACKEND_URL || 'http://127.0.0.1:5010';

// Simple fetch-like function using http module
function fetch(url, options = {}) {
  return new Promise((resolve, reject) => {
    const urlObj = new URL(url);
    const client = http;
    
    const req = client.request({
      hostname: urlObj.hostname,
      port: urlObj.port,
      path: urlObj.pathname,
      method: options.method || 'GET',
      headers: options.headers || {},
    }, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        resolve({
          ok: res.statusCode >= 200 && res.statusCode < 300,
          status: res.statusCode,
          json: async () => JSON.parse(data),
          text: async () => data,
        });
      });
    });
    
    req.on('error', reject);
    if (options.body) {
      req.write(options.body);
    }
    req.end();
  });
}

async function testBindingAPI() {
  console.log('🧪 Testing Binding Tag API Endpoints\n');

  let data1 = null; // Store data1 for Test 6

  // Test 1: Generate proof without binding tag (backward compatible)
  console.log('Test 1: Generate proof without binding tag');
  try {
    const res1 = await fetch(`${ZKP_BACKEND_URL}/zkp/generate-value-commitment-with-blinding`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        value: 1000000,
        blinding_hex: '0x4242424242424242424242424242424242424242424242424242424242424242',
      }),
    });
    data1 = await res1.json();
    console.log('✅ Response:', JSON.stringify(data1, null, 2));
    console.log('');
  } catch (error) {
    console.error('❌ Error:', error.message);
    return;
  }

  // Test 2: Generate proof with binding tag
  console.log('Test 2: Generate proof with binding tag');
  try {
    const bindingTag = '0xb3d9660812695cf688a896d66e3349c1eb1e0ceb81307d2360f0f1ca3a3ad875';
    const res2 = await fetch(`${ZKP_BACKEND_URL}/zkp/generate-value-commitment-with-binding`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        value: 1000000,
        blinding_hex: '0x4242424242424242424242424242424242424242424242424242424242424242',
        binding_tag_hex: bindingTag,
      }),
    });
    const data2 = await res2.json();
    console.log('✅ Response:', JSON.stringify(data2, null, 2));
    
    // Test 3: Verify proof with correct binding tag
    console.log('\nTest 3: Verify proof with correct binding tag');
    const res3 = await fetch(`${ZKP_BACKEND_URL}/zkp/verify-value-commitment`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        commitment: data2.commitment,
        proof: data2.proof,
        binding_tag_hex: bindingTag,
      }),
    });
    const data3 = await res3.json();
    console.log('✅ Verification result:', JSON.stringify(data3, null, 2));
    
    // Test 4: Verify proof with wrong binding tag (should fail)
    console.log('\nTest 4: Verify proof with wrong binding tag (should fail)');
    const wrongBindingTag = '0x' + '0'.repeat(64);
    const res4 = await fetch(`${ZKP_BACKEND_URL}/zkp/verify-value-commitment`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        commitment: data2.commitment,
        proof: data2.proof,
        binding_tag_hex: wrongBindingTag,
      }),
    });
    const data4 = await res4.json();
    console.log('✅ Verification result (wrong tag):', JSON.stringify(data4, null, 2));
    console.log(`   Expected: verified=false, Got: verified=${data4.verified}`);
    if (data4.verified === false) {
      console.log('   ✅ Test 4 PASSED: Wrong binding tag correctly rejected');
    } else {
      console.log('   ❌ Test 4 FAILED: Wrong binding tag should be rejected');
    }
    
    // Test 5: Verify proof without binding tag when it was generated with binding tag (should fail)
    console.log('\nTest 5: Verify proof without binding tag (generated with binding tag)');
    const res5 = await fetch(`${ZKP_BACKEND_URL}/zkp/verify-value-commitment`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        commitment: data2.commitment,
        proof: data2.proof,
        // No binding_tag_hex provided
      }),
    });
    const data5 = await res5.json();
    console.log('✅ Verification result (no tag):', JSON.stringify(data5, null, 2));
    console.log(`   Expected: verified=false, Got: verified=${data5.verified}`);
    if (data5.verified === false) {
      console.log('   ✅ Test 5 PASSED: Proof without binding tag correctly rejected');
    } else {
      console.log('   ❌ Test 5 FAILED: Proof without binding tag should be rejected');
    }
    
    // Test 6: Verify proof without binding tag when it was generated without binding tag (should work)
    console.log('\nTest 6: Verify proof without binding tag (generated without binding tag)');
    const res6 = await fetch(`${ZKP_BACKEND_URL}/zkp/verify-value-commitment`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        commitment: data1.commitment,
        proof: data1.proof,
        // No binding_tag_hex provided (backward compatible)
      }),
    });
    const data6 = await res6.json();
    console.log('✅ Verification result (backward compatible):', JSON.stringify(data6, null, 2));
    console.log(`   Expected: verified=true, Got: verified=${data6.verified}`);
    if (data6.verified === true) {
      console.log('   ✅ Test 6 PASSED: Backward compatibility works');
    } else {
      console.log('   ❌ Test 6 FAILED: Backward compatibility should work');
    }
    
    console.log('\n✅ API tests complete!');
  } catch (error) {
    console.error('❌ Error:', error.message);
  }
}

// Run tests
testBindingAPI().catch(console.error);


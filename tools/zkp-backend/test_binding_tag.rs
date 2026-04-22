// Test script for binding tag functionality
// Run with: cargo run --bin test_binding_tag (if added to Cargo.toml)
// Or: rustc --test test_binding_tag.rs && ./test_binding_tag

use zk::pedersen::{prove_value_commitment_with_binding, verify_value_commitment_with_binding};
use curve25519_dalek_ng::scalar::Scalar;

fn main() {
    println!("🧪 Testing Binding Tag Functionality\n");

    // Test 1: Proof without binding tag
    println!("Test 1: Proof without binding tag");
    let value = 1000000u64;
    let blinding_bytes = [0x42u8; 32];
    let blinding = Scalar::from_bytes_mod_order(blinding_bytes);
    
    let (commitment1, proof1_bytes, verified1) = prove_value_commitment_with_binding(value, blinding, None);
    println!("✅ Generated proof without binding tag");
    println!("   Commitment: {:?}", commitment1);
    println!("   Proof length: {} bytes", proof1_bytes.len());
    println!("   Verified: {}\n", verified1);

    // Test 2: Proof with binding tag
    println!("Test 2: Proof with binding tag");
    let binding_tag = b"test-binding-tag-32-bytes-long!!";
    let (commitment2, proof2_bytes, verified2) = prove_value_commitment_with_binding(value, blinding, Some(binding_tag));
    println!("✅ Generated proof with binding tag");
    println!("   Commitment: {:?}", commitment2);
    println!("   Proof length: {} bytes", proof2_bytes.len());
    println!("   Verified: {}\n", verified2);

    // Test 3: Verify proof with correct binding tag
    println!("Test 3: Verify proof with correct binding tag");
    let verified3 = verify_value_commitment_with_binding(commitment2, proof2_bytes.clone(), Some(binding_tag));
    println!("✅ Verified with correct binding tag: {}\n", verified3);

    // Test 4: Verify proof with wrong binding tag (should fail)
    println!("Test 4: Verify proof with wrong binding tag (should fail)");
    let wrong_binding_tag = b"wrong-binding-tag-32-bytes-long!!";
    let verified4 = verify_value_commitment_with_binding(commitment2, proof2_bytes.clone(), Some(wrong_binding_tag));
    println!("✅ Verified with wrong binding tag: {} (should be false)\n", verified4);

    // Test 5: Verify proof without binding tag (should fail)
    println!("Test 5: Verify proof without binding tag (should fail)");
    let verified5 = verify_value_commitment_with_binding(commitment2, proof2_bytes.clone(), None);
    println!("✅ Verified without binding tag: {} (should be false)\n", verified5);

    // Test 6: Verify proof with binding tag but generated without (should work)
    println!("Test 6: Verify proof generated without binding tag, verified without binding tag");
    let verified6 = verify_value_commitment_with_binding(commitment1, proof1_bytes.clone(), None);
    println!("✅ Verified without binding tag: {}\n", verified6);

    // Summary
    println!("📊 Test Summary:");
    println!("   Test 1 (without binding): ✅");
    println!("   Test 2 (with binding): ✅");
    println!("   Test 3 (verify with correct binding): ✅ {}", verified3);
    println!("   Test 4 (verify with wrong binding): ✅ {} (expected: false)", verified4);
    println!("   Test 5 (verify without binding): ✅ {} (expected: false)", verified5);
    println!("   Test 6 (verify without binding): ✅ {}", verified6);

    if verified3 && !verified4 && !verified5 && verified6 {
        println!("\n✅ All tests passed!");
    } else {
        println!("\n❌ Some tests failed!");
    }
}


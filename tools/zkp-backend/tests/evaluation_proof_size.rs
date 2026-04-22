//! Test 3.1: Proof Size Measurement
//! Measures Bulletproofs proof size for different value ranges (32-bit and 64-bit)

use bulletproof_demo::zk::pedersen::prove_value_commitment_with_binding_and_range;
use curve25519_dalek_ng::scalar::Scalar;
use rand::rngs::OsRng;
use rand::RngCore;

fn main() {
    println!("🧪 Test 3.1: Proof Size Measurement\n");

    // Fixed value for testing (within both 32-bit and 64-bit ranges)
    let value = 1000000u64;
    
    // Generate a fixed blinding factor for reproducibility
    let mut rng = OsRng;
    let mut blinding_bytes = [0u8; 32];
    rng.fill_bytes(&mut blinding_bytes);
    let blinding = Scalar::from_bytes_mod_order(blinding_bytes);
    
    // Binding tag (32 bytes) - typical size for our use case
    let binding_tag = b"test-binding-tag-32-bytes-long!!";

    // Test 32-bit range proof
    println!("=== 32-bit Range Proof ([0, 2^32)) ===");
    let (_commitment_32, proof_bytes_32, verified_32) = prove_value_commitment_with_binding_and_range(
        value,
        blinding,
        Some(binding_tag),
        32,
    );
    
    let commitment_size_32 = 32; // CompressedRistretto is always 32 bytes
    let proof_size_32 = proof_bytes_32.len();
    let binding_tag_size = 32; // Binding tag is 32 bytes
    let total_size_32 = commitment_size_32 + proof_size_32 + binding_tag_size;
    
    println!("  Commitment size: {} bytes", commitment_size_32);
    println!("  Proof size: {} bytes", proof_size_32);
    println!("  Binding tag size: {} bytes", binding_tag_size);
    println!("  Total size: {} bytes", total_size_32);
    println!("  Verified: {}\n", verified_32);

    // Test 64-bit range proof
    println!("=== 64-bit Range Proof ([0, 2^64)) ===");
    let (_commitment_64, proof_bytes_64, verified_64) = prove_value_commitment_with_binding_and_range(
        value,
        blinding,
        Some(binding_tag),
        64,
    );
    
    let commitment_size_64 = 32; // CompressedRistretto is always 32 bytes
    let proof_size_64 = proof_bytes_64.len();
    let total_size_64 = commitment_size_64 + proof_size_64 + binding_tag_size;
    
    println!("  Commitment size: {} bytes", commitment_size_64);
    println!("  Proof size: {} bytes", proof_size_64);
    println!("  Binding tag size: {} bytes", binding_tag_size);
    println!("  Total size: {} bytes", total_size_64);
    println!("  Verified: {}\n", verified_64);

    // Summary
    println!("=== Summary ===");
    println!("32-bit range proof size: {} bytes", proof_size_32);
    println!("64-bit range proof size: {} bytes", proof_size_64);
    println!("Total size (32-bit): {} bytes (commitment {} + proof {} + binding tag {})", 
             total_size_32, commitment_size_32, proof_size_32, binding_tag_size);
    println!("Total size (64-bit): {} bytes (commitment {} + proof {} + binding tag {})", 
             total_size_64, commitment_size_64, proof_size_64, binding_tag_size);
    
    // Verify both proofs are valid
    assert!(verified_32, "32-bit proof should verify");
    assert!(verified_64, "64-bit proof should verify");
    
    println!("\n✅ All tests passed!");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_proof_sizes() {
        println!("\n🧪 Test 3.1: Proof Size Measurement\n");

        let value = 1000000u64;
        let mut rng = OsRng;
        let mut blinding_bytes = [0u8; 32];
        rng.fill_bytes(&mut blinding_bytes);
        let blinding = Scalar::from_bytes_mod_order(blinding_bytes);
        let binding_tag = b"test-binding-tag-32-bytes-long!!";

        // Test 32-bit range proof
        println!("=== 32-bit Range Proof ([0, 2^32)) ===");
        let (_commitment_32, proof_bytes_32, verified_32) = prove_value_commitment_with_binding_and_range(
            value,
            blinding,
            Some(binding_tag),
            32,
        );
        
        let commitment_size_32 = 32; // CompressedRistretto is always 32 bytes
        let proof_size_32 = proof_bytes_32.len();
        let binding_tag_size = 32; // Binding tag is 32 bytes
        let total_size_32 = commitment_size_32 + proof_size_32 + binding_tag_size;
        
        println!("  Commitment size: {} bytes", commitment_size_32);
        println!("  Proof size: {} bytes", proof_size_32);
        println!("  Binding tag size: {} bytes", binding_tag_size);
        println!("  Total size: {} bytes", total_size_32);
        println!("  Verified: {}\n", verified_32);

        // Test 64-bit range proof
        println!("=== 64-bit Range Proof ([0, 2^64)) ===");
        let (_commitment_64, proof_bytes_64, verified_64) = prove_value_commitment_with_binding_and_range(
            value,
            blinding,
            Some(binding_tag),
            64,
        );
        
        let commitment_size_64 = 32; // CompressedRistretto is always 32 bytes
        let proof_size_64 = proof_bytes_64.len();
        let total_size_64 = commitment_size_64 + proof_size_64 + binding_tag_size;
        
        println!("  Commitment size: {} bytes", commitment_size_64);
        println!("  Proof size: {} bytes", proof_size_64);
        println!("  Binding tag size: {} bytes", binding_tag_size);
        println!("  Total size: {} bytes", total_size_64);
        println!("  Verified: {}\n", verified_64);

        // Summary
        println!("=== Summary ===");
        println!("32-bit range proof size: {} bytes", proof_size_32);
        println!("64-bit range proof size: {} bytes", proof_size_64);
        println!("Total size (32-bit): {} bytes (commitment {} + proof {} + binding tag {})", 
                 total_size_32, commitment_size_32, proof_size_32, binding_tag_size);
        println!("Total size (64-bit): {} bytes (commitment {} + proof {} + binding tag {})", 
                 total_size_64, commitment_size_64, proof_size_64, binding_tag_size);

        // Assertions
        assert!(verified_32, "32-bit proof should verify");
        assert!(proof_bytes_32.len() > 0, "32-bit proof should have non-zero size");
        assert!(verified_64, "64-bit proof should verify");
        assert!(proof_bytes_64.len() > 0, "64-bit proof should have non-zero size");
        assert!(proof_bytes_64.len() >= proof_bytes_32.len(), 
                "64-bit proof should be at least as large as 32-bit proof");
        
        println!("\n✅ All tests passed!");
    }
}


//! Test 3.4: BP+ Proof Size Measurement
//! Measures Bulletproofs-Plus proof size for transaction ID proofs (4 × 64-bit limbs = 256-bit)

use bulletproof_demo::zk::bp_plus_pedersen::{prove_txid_commitment, verify_txid_commitment};

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_bpplus_proof_sizes() {
        println!("\n🧪 Test 3.4: BP+ Proof Size Measurement (Transaction ID)\n");

        // Use fixed test parameters (same approach as BP tests for fair comparison)
        let tx_hash: [u8; 32] = [
            0x12, 0x34, 0x56, 0x78, 0x9a, 0xbc, 0xde, 0xf0,
            0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88,
            0x99, 0xaa, 0xbb, 0xcc, 0xdd, 0xee, 0xff, 0x00,
            0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
        ];

        println!("=== BP+ Transaction ID Proof (4 × 64-bit limbs = 256-bit) ===");
        let (commitments, proof_bytes) = prove_txid_commitment(tx_hash);
        
        let commitment_size = commitments.len() * 32; // Each CompressedRistretto is 32 bytes
        let proof_size = proof_bytes.len();
        let total_size = commitment_size + proof_size;
        
        println!("  Number of commitments: {}", commitments.len());
        println!("  Total commitment size: {} bytes ({} × 32 bytes)", commitment_size, commitments.len());
        println!("  Proof size: {} bytes", proof_size);
        println!("  Total size: {} bytes", total_size);
        
        // Verify the proof
        let verified = verify_txid_commitment(commitments.clone(), proof_bytes.clone());
        println!("  Verified: {}\n", verified);

        // Summary
        println!("=== Summary ===");
        println!("BP+ proof size (4×64-bit): {} bytes", proof_size);
        println!("Total commitments size: {} bytes (4 commitments × 32 bytes)", commitment_size);
        println!("Total size (commitments + proof): {} bytes", total_size);
        println!("Size per limb: {} bytes (proof only)", proof_size as f64 / 4.0);

        // Assertions
        assert!(verified, "BP+ proof should verify");
        assert!(proof_bytes.len() > 0, "BP+ proof should have non-zero size");
        assert_eq!(commitments.len(), 4, "Should have 4 commitments (one per limb)");
        assert!(commitment_size == 128, "4 commitments × 32 bytes = 128 bytes");
        
        println!("\n✅ All tests passed!");
    }

    #[test]
    fn test_bpplus_proof_size_consistency() {
        println!("\n🧪 Test: BP+ Proof Size Consistency\n");

        let mut proof_sizes = Vec::new();
        let mut commitment_sizes = Vec::new();

        // Generate a few proofs with different fixed hashes to check size consistency
        // (BP+ proof size should be constant regardless of input values)
        // Reduced to 3 proofs for faster testing (matching BP test approach of 2 proofs)
        let test_hashes: [[u8; 32]; 3] = [
            [0x12, 0x34, 0x56, 0x78, 0x9a, 0xbc, 0xde, 0xf0, 0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88, 0x99, 0xaa, 0xbb, 0xcc, 0xdd, 0xee, 0xff, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08],
            [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00],
            [0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff],
        ];

        for (i, &tx_hash) in test_hashes.iter().enumerate() {
            let (commitments, proof_bytes) = prove_txid_commitment(tx_hash);
            proof_sizes.push(proof_bytes.len());
            commitment_sizes.push(commitments.len() * 32);
            
            let verified = verify_txid_commitment(commitments, proof_bytes);
            assert!(verified, "Proof {} should verify", i);
        }

        // Check that all proofs have the same size (BP+ proofs should be deterministic in size)
        let first_proof_size = proof_sizes[0];
        let first_commitment_size = commitment_sizes[0];
        
        for (i, &size) in proof_sizes.iter().enumerate() {
            assert_eq!(size, first_proof_size, "Proof {} should have same size as first proof", i);
        }
        
        for (i, &size) in commitment_sizes.iter().enumerate() {
            assert_eq!(size, first_commitment_size, "Commitments {} should have same size as first", i);
        }

        println!("Proof size consistency: All {} proofs have size {} bytes", proof_sizes.len(), first_proof_size);
        println!("Commitment size consistency: All {} have size {} bytes", commitment_sizes.len(), first_commitment_size);
        
        println!("\n✅ All consistency tests passed!");
    }
}


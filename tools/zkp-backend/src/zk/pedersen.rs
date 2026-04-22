use bulletproofs::r1cs::{ConstraintSystem, Prover, Verifier};
use bulletproofs::{BulletproofGens, PedersenGens};
use bulletproofs::RangeProof;
use curve25519_dalek_ng::ristretto::CompressedRistretto;
use curve25519_dalek_ng::scalar::Scalar;
use merlin::Transcript;
use rand::rngs::OsRng;
use rand::RngCore;

pub fn prove_equal_42() {
    // Step 1: Secret value
    let secret_value: u64 = 42;

    // Step 2: Generators
    let pc_gens = PedersenGens::default();
    let bp_gens = BulletproofGens::new(64, 1);
    let mut rng = OsRng;

    // Step 3: Prover commits to secret
    let mut prover_transcript = Transcript::new(b"ZKPDemo");
    let (proof, committed_value) = {
        let mut prover = Prover::new(&pc_gens, &mut prover_transcript);

        // Blinding factor (random scalar)
        let mut bytes = [0u8; 64];
        rng.fill_bytes(&mut bytes);
        let blinding = Scalar::from_bytes_mod_order_wide(&bytes);

        // Commit to secret value with blinding
        let (com, var) = prover.commit(Scalar::from(secret_value), blinding);

        // Constrain: var == 42
        prover.constrain(var - Scalar::from(42u64));

        // Create proof
        let proof = prover.prove(&bp_gens).unwrap();
        (proof, com)
    };

    // Step 4: Verifier checks the proof
    let mut verifier_transcript = Transcript::new(b"ZKPDemo");
    let verified = {
        let mut verifier = Verifier::new(&mut verifier_transcript);
        let var = verifier.commit(committed_value);
        verifier.constrain(var - Scalar::from(42u64));
        verifier.verify(&proof, &pc_gens, &bp_gens).is_ok()
    };

    println!("✅ Proof verified? {}", verified);
}

/// Proves knowledge of a value such that Pedersen(value, r) == commitment and value in [0, 2^64)
pub fn prove_value_commitment(value: u64) -> (CompressedRistretto, Vec<u8>, bool) {
    println!("▶️ Running: Bulletproofs range proof for value using Pedersen commitment");

    let mut rng = OsRng;

    // Generate random blinding factor
    let mut bytes = [0u8; 32];
    rng.fill_bytes(&mut bytes);
    let blinding = Scalar::from_bytes_mod_order(bytes);

    prove_value_commitment_with_blinding(value, blinding)
}

/// Proves knowledge of a value with a specific blinding factor (deterministic)
/// This allows seller and buyer to generate the same commitment
pub fn prove_value_commitment_with_blinding(
    value: u64,
    blinding: Scalar,
) -> (CompressedRistretto, Vec<u8>, bool) {
    // Call with no binding tag for backward compatibility
    prove_value_commitment_with_binding(value, blinding, None)
}

/// Proves knowledge of a value with a specific blinding factor, binding tag, and bit range
/// The binding tag binds the proof to VC context to prevent replay attacks
/// bit_range: number of bits for the range proof (e.g., 32 for [0, 2^32), 64 for [0, 2^64))
#[allow(dead_code)]
pub fn prove_value_commitment_with_binding_and_range(
    value: u64,
    blinding: Scalar,
    binding_tag: Option<&[u8]>,
    bit_range: usize,
) -> (CompressedRistretto, Vec<u8>, bool) {
    let pc_gens = PedersenGens::default();
    let bp_gens = BulletproofGens::new(bit_range, 1); // variable bit range, 1 party

    // Prover phase: use RangeProof API with provided blinding and binding tag
    let mut transcript = Transcript::new(b"ValueRangeProof");
    
    // ✅ Add binding tag to transcript if provided
    if let Some(binding) = binding_tag {
        transcript.append_message(b"bind", binding);
    }
    
    let (proof, commitment) = RangeProof::prove_single(
        &bp_gens,
        &pc_gens,
        &mut transcript,
        value,
        &blinding,
        bit_range,
    ).expect("Range proof generation should not fail");
    let proof_bytes = proof.to_bytes();

    // Verifier phase (optional, for sanity check)
    let mut transcript = Transcript::new(b"ValueRangeProof");
    
    // ✅ Add binding tag to verification transcript if provided
    if let Some(binding) = binding_tag {
        transcript.append_message(b"bind", binding);
    }
    
    let verified = RangeProof::verify_single(
        &proof,
        &bp_gens,
        &pc_gens,
        &mut transcript,
        &commitment,
        bit_range,
    ).is_ok();

    (commitment, proof_bytes, verified)
}

/// Proves knowledge of a value with a specific blinding factor and binding tag
/// The binding tag binds the proof to VC context to prevent replay attacks
pub fn prove_value_commitment_with_binding(
    value: u64,
    blinding: Scalar,
    binding_tag: Option<&[u8]>,
) -> (CompressedRistretto, Vec<u8>, bool) {
    if binding_tag.is_some() {
        println!("▶️ Running: Bulletproofs range proof with binding tag");
    } else {
        println!("▶️ Running: Bulletproofs range proof for value with provided blinding factor");
    }

    let pc_gens = PedersenGens::default();
    let bp_gens = BulletproofGens::new(64, 1); // 64-bit range, 1 party

    // Prover phase: use RangeProof API with provided blinding and binding tag
    let mut transcript = Transcript::new(b"ValueRangeProof");
    
    // ✅ Add binding tag to transcript if provided
    if let Some(binding) = binding_tag {
        transcript.append_message(b"bind", binding);
        println!("   📎 Binding tag added to transcript: {} bytes", binding.len());
    }
    
    let (proof, commitment) = RangeProof::prove_single(
        &bp_gens,
        &pc_gens,
        &mut transcript,
        value,
        &blinding,
        64,
    ).expect("Range proof generation should not fail");
    let proof_bytes = proof.to_bytes();
    // commitment is already CompressedRistretto

    // Verifier phase (optional, for sanity check)
    let mut transcript = Transcript::new(b"ValueRangeProof");
    
    // ✅ Add binding tag to verification transcript if provided
    if let Some(binding) = binding_tag {
        transcript.append_message(b"bind", binding);
    }
    
    let verified = RangeProof::verify_single(
        &proof,
        &bp_gens,
        &pc_gens,
        &mut transcript,
        &commitment,
        64,
    ).is_ok();

    println!("✅ ZK Range proof of value commitment verified? {}", verified);

    (commitment, proof_bytes, verified)
}

/// Verifies the proof of a value commitment
pub fn verify_value_commitment(
    commitment: CompressedRistretto,
    proof_bytes: Vec<u8>
) -> bool {
    // Call with no binding tag for backward compatibility
    verify_value_commitment_with_binding(commitment, proof_bytes, None)
}

/// Verifies the proof of a value commitment with binding tag
pub fn verify_value_commitment_with_binding(
    commitment: CompressedRistretto,
    proof_bytes: Vec<u8>,
    binding_tag: Option<&[u8]>,
) -> bool {
    let pc_gens = PedersenGens::default();
    let bp_gens = BulletproofGens::new(64, 1);
    let mut transcript = Transcript::new(b"ValueRangeProof");
    
    // ✅ Add binding tag to verification transcript if provided
    if let Some(binding) = binding_tag {
        transcript.append_message(b"bind", binding);
    }
    
    let proof = match RangeProof::from_bytes(&proof_bytes) {
        Ok(p) => p,
        Err(_) => return false,
    };
    RangeProof::verify_single(
        &proof,
        &bp_gens,
        &pc_gens,
        &mut transcript,
        &commitment,
        64,
    ).is_ok()
}

#[cfg(test)]
mod value_commitment_tests {
    use super::*;

    #[test]
    fn test_valid_value_commitment_proof() {
        let value = 123456u64;
        let (commitment, proof_bytes, verified) = prove_value_commitment(value);
        assert!(verified, "Proof should verify locally");
        assert!(verify_value_commitment(commitment, proof_bytes), "Proof should verify with public verifier");
    }

    #[test]
    fn test_invalid_value_commitment_proof() {
        let value1 = 123456u64;
        let value2 = 654321u64;
        let (commitment1, proof_bytes, _) = prove_value_commitment(value1);
        // Try to verify proof_bytes against a different commitment
        let (commitment2, _, _) = prove_value_commitment(value2);
        assert!(!verify_value_commitment(commitment2, proof_bytes), "Proof for value1 should not verify for commitment2");
    }

    #[test]
    fn test_deterministic_commitment_with_blinding() {
        let value = 1000000u64;
        // Use a fixed blinding factor (deterministic)
        let blinding_bytes = [0x42u8; 32];
        let blinding = Scalar::from_bytes_mod_order(blinding_bytes);

        // Generate commitment twice with same blinding
        let (commitment1, proof1_bytes, verified1) = prove_value_commitment_with_blinding(value, blinding);
        let blinding2 = Scalar::from_bytes_mod_order(blinding_bytes);
        let (commitment2, proof2_bytes, verified2) = prove_value_commitment_with_blinding(value, blinding2);

        // Both should verify
        assert!(verified1, "First proof should verify");
        assert!(verified2, "Second proof should verify");

        // Commitments should be identical (same value + same blinding)
        assert_eq!(commitment1, commitment2, "Commitments should be identical with same blinding");

        // Proofs should be different (transcript randomness), but both should verify
        assert_ne!(proof1_bytes, proof2_bytes, "Proofs should be different due to transcript");
        assert!(verify_value_commitment(commitment1, proof1_bytes), "First proof should verify");
        assert!(verify_value_commitment(commitment2, proof2_bytes), "Second proof should verify");
    }

    #[test]
    fn test_binding_tag_functionality() {
        let value = 1000000u64;
        let blinding_bytes = [0x42u8; 32];
        let blinding = Scalar::from_bytes_mod_order(blinding_bytes);
        let binding_tag = b"test-binding-tag-32-bytes-long!!";

        // Test 1: Generate proof with binding tag
        let (commitment, proof_bytes, verified) = prove_value_commitment_with_binding(value, blinding, Some(binding_tag));
        assert!(verified, "Proof with binding tag should verify");

        // Test 2: Verify proof with correct binding tag
        let verified_correct = verify_value_commitment_with_binding(commitment, proof_bytes.clone(), Some(binding_tag));
        assert!(verified_correct, "Proof should verify with correct binding tag");

        // Test 3: Verify proof with wrong binding tag (should fail)
        let wrong_binding_tag = b"wrong-binding-tag-32-bytes-long!!";
        let verified_wrong = verify_value_commitment_with_binding(commitment, proof_bytes.clone(), Some(wrong_binding_tag));
        assert!(!verified_wrong, "Proof should not verify with wrong binding tag");

        // Test 4: Verify proof without binding tag (should fail if generated with binding tag)
        let verified_no_tag = verify_value_commitment_with_binding(commitment, proof_bytes.clone(), None);
        assert!(!verified_no_tag, "Proof generated with binding tag should not verify without binding tag");
    }

    #[test]
    fn test_backward_compatibility_without_binding_tag() {
        let value = 1000000u64;
        let blinding_bytes = [0x42u8; 32];
        let blinding = Scalar::from_bytes_mod_order(blinding_bytes);

        // Test: Generate proof without binding tag (backward compatible)
        let (commitment, proof_bytes, verified) = prove_value_commitment_with_binding(value, blinding, None);
        assert!(verified, "Proof without binding tag should verify");

        // Test: Verify proof without binding tag (backward compatible)
        let verified_no_tag = verify_value_commitment_with_binding(commitment, proof_bytes.clone(), None);
        assert!(verified_no_tag, "Proof generated without binding tag should verify without binding tag");
    }
}

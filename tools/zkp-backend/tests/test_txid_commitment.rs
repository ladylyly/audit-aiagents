//! Test TX hash commitment functionality
//! Step 1: Verify that prove_txid_commitment_from_hex works correctly

use bulletproof_demo::zk::txid_pedersen_proof::{prove_txid_commitment_from_hex, verify_txid_commitment};
use curve25519_dalek_ng::ristretto::CompressedRistretto;

#[test]
fn test_txid_commitment_from_hex() {
    println!("\n🧪 Testing TX Hash Commitment (Step 1)\n");
    
    // Sample Ethereum transaction hash (32 bytes)
    let tx_hash_hex = "0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef";
    
    println!("Input TX hash: {}", tx_hash_hex);
    
    // Generate commitment
    let (commitment, proof_bytes, verified) = prove_txid_commitment_from_hex(tx_hash_hex);
    
    println!("Commitment: {:?}", hex::encode(commitment.as_bytes()));
    println!("Proof size: {} bytes", proof_bytes.len());
    println!("Initial verification: {}", verified);
    
    // Verify the commitment
    let verification_result = verify_txid_commitment(commitment, proof_bytes);
    println!("Verification result: {}\n", verification_result);
    
    assert!(verified, "Initial verification should pass");
    assert!(verification_result, "Standalone verification should pass");
    
    println!("✅ Step 1 PASSED: TX hash commitment works correctly!");
}

#[test]
fn test_txid_commitment_verification() {
    println!("\n🧪 Testing TX Hash Commitment Verification\n");
    
    let tx_hash_hex = "0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890";
    
    let (commitment, proof_bytes, _) = prove_txid_commitment_from_hex(tx_hash_hex);
    
    // Test valid verification
    assert!(verify_txid_commitment(commitment.clone(), proof_bytes.clone()), 
            "Valid commitment should verify");
    
    // Test invalid commitment (wrong commitment)
    let fake_commitment_bytes = [0u8; 32];
    let fake_commitment = CompressedRistretto::from_slice(&fake_commitment_bytes);
    assert!(!verify_txid_commitment(fake_commitment, proof_bytes.clone()),
            "Fake commitment should not verify");
    
    // Test invalid proof (wrong proof)
    let fake_proof = vec![0u8; 100];
    assert!(!verify_txid_commitment(commitment, fake_proof),
            "Fake proof should not verify");
    
    println!("✅ Verification tests PASSED!");
}


//! Simple test to verify BP+ works correctly before running full benchmarks

use bulletproof_demo::zk::bp_plus_pedersen::{prove_txid_commitment, prove_txid_commitment_with_rng, verify_txid_commitment};
use std::time::Instant;
use rand::thread_rng;

#[test]
fn test_bpplus_simple() {
    println!("\n🧪 Simple BP+ Test\n");
    
    let tx_hash: [u8; 32] = [
        0x12, 0x34, 0x56, 0x78, 0x9a, 0xbc, 0xde, 0xf0,
        0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88,
        0x99, 0xaa, 0xbb, 0xcc, 0xdd, 0xee, 0xff, 0x00,
        0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
    ];
    
    println!("Test 1: Using OsRng (production version)...");
    let start = Instant::now();
    let (commitments1, proof_bytes1) = prove_txid_commitment(tx_hash);
    let gen_time1 = start.elapsed();
    println!("  Proof generated in {:.3} ms", gen_time1.as_nanos() as f64 / 1_000_000.0);
    println!("  Proof size: {} bytes", proof_bytes1.len());
    println!("  Commitments: {} ({} bytes total)", commitments1.len(), commitments1.len() * 32);
    
    let start = Instant::now();
    let verified1 = verify_txid_commitment(commitments1.clone(), proof_bytes1.clone());
    let verify_time1 = start.elapsed();
    println!("  Proof verified in {:.3} ms", verify_time1.as_nanos() as f64 / 1_000_000.0);
    println!("  Verified: {}\n", verified1);
    
    assert!(verified1, "BP+ proof should verify");
    
    println!("Test 2: Using ThreadRng (faster for testing)...");
    let mut rng = thread_rng();
    let start = Instant::now();
    let (commitments2, proof_bytes2) = prove_txid_commitment_with_rng(tx_hash, &mut rng);
    let gen_time2 = start.elapsed();
    println!("  Proof generated in {:.3} ms", gen_time2.as_nanos() as f64 / 1_000_000.0);
    println!("  Proof size: {} bytes", proof_bytes2.len());
    println!("  Commitments: {} ({} bytes total)", commitments2.len(), commitments2.len() * 32);
    
    let start = Instant::now();
    let verified2 = verify_txid_commitment(commitments2, proof_bytes2);
    let verify_time2 = start.elapsed();
    println!("  Proof verified in {:.3} ms", verify_time2.as_nanos() as f64 / 1_000_000.0);
    println!("  Verified: {}\n", verified2);
    
    assert!(verified2, "BP+ proof should verify");
    
    println!("✅ BP+ implementation verified!");
    println!("   Both OsRng and ThreadRng versions work correctly.");
    println!("   ThreadRng is faster for benchmarking (no entropy blocking).");
}


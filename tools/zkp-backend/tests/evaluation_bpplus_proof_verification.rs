//! Test 3.6: BP+ Proof Verification Time
//! Measures time to verify a BP+ range proof for transaction IDs (4 × 64-bit limbs)
//! Structured identically to BP verification test for fair comparison

use bulletproof_demo::zk::bp_plus_pedersen::{prove_txid_commitment, verify_txid_commitment};
use std::time::Instant;
use sha2::{Sha256, Digest};

// Helper function to compute binding tag (matching BP test structure)
// Note: BP+ doesn't use binding tags, but we measure this for structural consistency
fn compute_binding_tag(
    chain_id: &str,
    escrow_addr: &[u8],
    product_id: u64,
    stage: u8,
    schema_version: &str,
    previous_vc_cid: Option<&str>,
) -> Vec<u8> {
    let mut hasher = Sha256::new();
    hasher.update(chain_id.as_bytes());
    hasher.update(escrow_addr);
    hasher.update(&product_id.to_le_bytes());
    hasher.update(&[stage]);
    hasher.update(schema_version.as_bytes());
    if let Some(cid) = previous_vc_cid {
        hasher.update(cid.as_bytes());
    }
    hasher.finalize().to_vec()
}

// Statistics calculation (identical to BP tests)
struct Stats {
    median: f64,
    q1: f64,
    q3: f64,
    iqr: f64,
    min: f64,
    max: f64,
    mean: f64,
    std_dev: f64,
}

fn calculate_stats(times: &[f64]) -> Stats {
    let mut sorted = times.to_vec();
    sorted.sort_by(|a, b| a.partial_cmp(b).unwrap());
    
    let n = sorted.len();
    let median = if n % 2 == 0 {
        (sorted[n / 2 - 1] + sorted[n / 2]) / 2.0
    } else {
        sorted[n / 2]
    };
    
    let q1_idx = n / 4;
    let q3_idx = 3 * n / 4;
    let q1 = sorted[q1_idx];
    let q3 = sorted[q3_idx];
    let iqr = q3 - q1;
    
    let min = sorted[0];
    let max = sorted[n - 1];
    
    let mean = times.iter().sum::<f64>() / n as f64;
    let variance = times.iter().map(|x| (x - mean).powi(2)).sum::<f64>() / n as f64;
    let std_dev = variance.sqrt();
    
    Stats {
        median,
        q1,
        q3,
        iqr,
        min,
        max,
        mean,
        std_dev,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_bpplus_proof_verification_time() {
        println!("\n🧪 Test 3.6: BP+ Proof Verification Time (4 × 64-bit limbs)\n");

        const RUNS: usize = 100;
        
        // Test parameters (identical to BP tests for fair comparison)
        let escrow_addr = b"0xc448142dF27D18A7bE5a439589320429AB18855c";
        let chain_id = "11155111";
        let product_id = 14u64;
        let stage = 0u8;
        let schema_version = "1.0";
        let previous_vc_cid: Option<&str> = None;
        
        // Fixed transaction hash (derived from test parameters for consistency)
        let tx_hash: [u8; 32] = [
            0x12, 0x34, 0x56, 0x78, 0x9a, 0xbc, 0xde, 0xf0,
            0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88,
            0x99, 0xaa, 0xbb, 0xcc, 0xdd, 0xee, 0xff, 0x00,
            0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
        ];

        // Generate a valid proof once (before timing verification) - identical structure to BP tests
        println!("Generating test proof...");
        let _binding_tag = compute_binding_tag(chain_id, escrow_addr, product_id, stage, schema_version, previous_vc_cid);
        
        let (commitments, proof_bytes) = prove_txid_commitment(tx_hash);
        let verified_gen = verify_txid_commitment(commitments.clone(), proof_bytes.clone());
        
        assert!(verified_gen, "Generated proof should verify");
        println!("Proof generated successfully ({} commitments, {} bytes proof).\n", commitments.len(), proof_bytes.len());

        let mut setup_times = Vec::new();
        let mut verify_times = Vec::new();
        let mut total_times = Vec::new();

        println!("Running {} verification iterations...\n", RUNS);

        // Warm-up run (not counted) - identical structure to BP tests
        let _ = verify_txid_commitment(commitments.clone(), proof_bytes.clone());

        for i in 0..RUNS {
            let total_start = Instant::now();

            // Setup public inputs (commitments and proof parsing)
            // This matches BP's "Setup public inputs $(C,t)$" operation
            // Setup involves: creating generators, creating parameters, decompressing commitments, parsing proof
            let setup_start = Instant::now();
            use tari_bulletproofs_plus::{
                generators::pedersen_gens::ExtensionDegree,
                range_parameters::RangeParameters,
                range_proof::VerifyAction,
                range_statement::RangeStatement,
                ristretto::{create_pedersen_gens_with_extension_degree, RistrettoRangeProof},
            };
            use merlin::Transcript;
            
            let pc_gens = create_pedersen_gens_with_extension_degree(ExtensionDegree::DefaultPedersen);
            let params = RangeParameters::init(64, 4, pc_gens.clone()).unwrap();
            
            // Decompress commitments
            let decompressed: Vec<_> = commitments.iter()
                .map(|c| c.decompress().unwrap())
                .collect();
            
            let statement = RangeStatement::init(
                params,
                decompressed,
                vec![None; 4],
                None
            ).unwrap();
            
            // Parse proof from bytes (part of setup)
            let proof = match RistrettoRangeProof::from_bytes(&proof_bytes) {
                Ok(p) => p,
                Err(_) => {
                    panic!("Failed to parse proof");
                }
            };
            let setup_time = setup_start.elapsed();
            setup_times.push(setup_time.as_nanos() as f64 / 1_000_000.0);

            // Verify proof (the actual RistrettoRangeProof::verify_batch operation)
            // This matches BP's "Verify range proof" operation
            let verify_start = Instant::now();
            let mut transcript = Transcript::new(b"TxID-BP+-256bit");
            let verified = RistrettoRangeProof::verify_batch(
                &mut vec![transcript],
                &vec![statement],
                &vec![proof],
                VerifyAction::VerifyOnly,
            ).is_ok();
            let verify_time = verify_start.elapsed();
            verify_times.push(verify_time.as_nanos() as f64 / 1_000_000.0);

            let total_time = total_start.elapsed();
            total_times.push(total_time.as_nanos() as f64 / 1_000_000.0);

            assert!(verified, "Proof should verify correctly");

            if (i + 1) % 10 == 0 {
                print!(".");
                use std::io::Write;
                std::io::stdout().flush().unwrap();
            }
        }
        println!("\n");

        // Calculate statistics (identical to BP tests)
        let setup_stats = calculate_stats(&setup_times);
        let verify_stats = calculate_stats(&verify_times);
        let total_stats = calculate_stats(&total_times);

        // Output results (identical format to BP tests)
        println!("=== BP+ Proof Verification Time Statistics ({} runs) ===\n", RUNS);
        
        println!("Setup public inputs (4 commitments, proof parsing):");
        println!("  Median: {:.3} ms", setup_stats.median);
        println!("  IQR: {:.3} ms (Q1: {:.3}, Q3: {:.3})", setup_stats.iqr, setup_stats.q1, setup_stats.q3);
        println!("  Min: {:.3} ms", setup_stats.min);
        println!("  Max: {:.3} ms", setup_stats.max);
        println!("  Mean: {:.3} ms", setup_stats.mean);
        println!("  Std Dev: {:.3} ms\n", setup_stats.std_dev);

        println!("Verify BP+ range proof (4 × 64-bit):");
        println!("  Median: {:.3} ms", verify_stats.median);
        println!("  IQR: {:.3} ms (Q1: {:.3}, Q3: {:.3})", verify_stats.iqr, verify_stats.q1, verify_stats.q3);
        println!("  Min: {:.3} ms", verify_stats.min);
        println!("  Max: {:.3} ms", verify_stats.max);
        println!("  Mean: {:.3} ms", verify_stats.mean);
        println!("  Std Dev: {:.3} ms\n", verify_stats.std_dev);

        println!("Total verification time:");
        println!("  Median: {:.3} ms", total_stats.median);
        println!("  IQR: {:.3} ms (Q1: {:.3}, Q3: {:.3})", total_stats.iqr, total_stats.q1, total_stats.q3);
        println!("  Min: {:.3} ms", total_stats.min);
        println!("  Max: {:.3} ms", total_stats.max);
        println!("  Mean: {:.3} ms", total_stats.mean);
        println!("  Std Dev: {:.3} ms\n", total_stats.std_dev);

        println!("=== Summary ===");
        println!("Setup public inputs (4 commitments): median={:.3} ms, IQR={:.3} ms, min={:.3} ms, max={:.3} ms", 
                 setup_stats.median, setup_stats.iqr, setup_stats.min, setup_stats.max);
        println!("Verify BP+ range proof: median={:.3} ms, IQR={:.3} ms, min={:.3} ms, max={:.3} ms", 
                 verify_stats.median, verify_stats.iqr, verify_stats.min, verify_stats.max);
        println!("Total verification time: median={:.3} ms, IQR={:.3} ms, min={:.3} ms, max={:.3} ms", 
                 total_stats.median, total_stats.iqr, total_stats.min, total_stats.max);

        // Verify that all operations completed successfully
        assert!(setup_stats.median >= 0.0, "Setup should take time");
        assert!(verify_stats.median > 0.0, "Verification should take time");
        assert!(total_stats.median > 0.0, "Total verification should take time");
        
        println!("\n✅ All tests passed!");
    }
}

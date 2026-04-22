use bulletproof_demo::zk;

use curve25519_dalek_ng::ristretto::CompressedRistretto as NgCompressed;
use curve25519_dalek_ng::scalar::Scalar;
use rand::rngs::OsRng;
use rand::RngCore;
use serde::Deserialize;
use serde_json::json;
use std::io::Read;

#[derive(Deserialize)]
struct CliInput {
    op: Option<String>,
    commitment: Option<String>,
    proof: Option<String>,
    binding_tag_hex: Option<String>,
    value: Option<u64>,
    blinding_hex: Option<String>,
}

fn strip_0x(value: &str) -> &str {
    value.strip_prefix("0x").unwrap_or(value)
}

fn parse_commitment_32(value: &str) -> Result<[u8; 32], String> {
    let bytes = hex::decode(strip_0x(value)).map_err(|e| format!("bad commitment hex: {e}"))?;
    if bytes.len() != 32 {
        return Err(format!(
            "bad commitment length: expected 32 bytes, got {}",
            bytes.len()
        ));
    }
    let mut arr = [0u8; 32];
    arr.copy_from_slice(&bytes);
    Ok(arr)
}

fn parse_proof(value: &str) -> Result<Vec<u8>, String> {
    hex::decode(strip_0x(value)).map_err(|e| format!("bad proof hex: {e}"))
}

fn parse_binding_tag(value: Option<String>) -> Result<Option<Vec<u8>>, String> {
    let Some(tag) = value else {
        return Ok(None);
    };
    let bytes = hex::decode(strip_0x(&tag)).map_err(|e| format!("bad binding_tag_hex: {e}"))?;
    if bytes.len() != 32 {
        return Err(format!(
            "bad binding_tag_hex length: expected 32 bytes, got {}",
            bytes.len()
        ));
    }
    Ok(Some(bytes))
}

fn parse_blinding_32(value: Option<String>) -> Result<Option<[u8; 32]>, String> {
    let Some(hex_s) = value else {
        return Ok(None);
    };
    let bytes = hex::decode(strip_0x(&hex_s)).map_err(|e| format!("bad blinding_hex: {e}"))?;
    if bytes.len() != 32 {
        return Err(format!(
            "bad blinding_hex length: expected 32 bytes, got {}",
            bytes.len()
        ));
    }
    let mut arr = [0u8; 32];
    arr.copy_from_slice(&bytes);
    Ok(Some(arr))
}

fn read_input() -> Result<CliInput, String> {
    let mut buf = String::new();
    std::io::stdin()
        .read_to_string(&mut buf)
        .map_err(|e| format!("failed reading stdin: {e}"))?;
    if buf.trim().is_empty() {
        return Err("empty stdin".to_string());
    }
    serde_json::from_str(&buf).map_err(|e| format!("invalid json: {e}"))
}

fn main() {
    let cli_arg = std::env::args().nth(1);
    let input = match read_input() {
        Ok(v) => v,
        Err(err) => {
            println!("{}", json!({ "verified": false, "error": err }));
            std::process::exit(1);
        }
    };

    let op = cli_arg
        .or(input.op.clone())
        .unwrap_or_else(|| "verify-value-commitment".to_string());

    match op.as_str() {
        "generate-value-commitment" => {
            let value = match input.value {
                Some(v) => v,
                None => {
                    println!("{}", json!({ "verified": false, "error": "missing value for generate-value-commitment" }));
                    std::process::exit(1);
                }
            };

            let binding_tag = match parse_binding_tag(input.binding_tag_hex) {
                Ok(v) => v,
                Err(err) => {
                    println!("{}", json!({ "verified": false, "error": err }));
                    std::process::exit(1);
                }
            };

            let blinding_bytes = match parse_blinding_32(input.blinding_hex) {
                Ok(v) => v,
                Err(err) => {
                    println!("{}", json!({ "verified": false, "error": err }));
                    std::process::exit(1);
                }
            };

            let (commitment, proof, verified) = if let Some(bytes) = blinding_bytes {
                let blinding = Scalar::from_bytes_mod_order(bytes);
                zk::pedersen::prove_value_commitment_with_binding(
                    value,
                    blinding,
                    binding_tag.as_ref().map(|b| b.as_slice()),
                )
            } else if binding_tag.is_some() {
                let mut bytes = [0u8; 32];
                OsRng.fill_bytes(&mut bytes);
                let blinding = Scalar::from_bytes_mod_order(bytes);
                zk::pedersen::prove_value_commitment_with_binding(
                    value,
                    blinding,
                    binding_tag.as_ref().map(|b| b.as_slice()),
                )
            } else {
                zk::pedersen::prove_value_commitment(value)
            };

            println!(
                "{}",
                json!({
                    "verified": verified,
                    "value": value,
                    "commitment": format!("0x{}", hex::encode(commitment.as_bytes())),
                    "proof": format!("0x{}", hex::encode(proof)),
                    "binding_tag_hex": binding_tag.map(|b| format!("0x{}", hex::encode(b))),
                })
            );
        }
        "verify-value-commitment" | "verify-tx-hash-commitment" => {
            let commitment_str = match input.commitment.as_deref() {
                Some(v) => v,
                None => {
                    println!("{}", json!({ "verified": false, "error": "missing commitment" }));
                    std::process::exit(1);
                }
            };
            let proof_str = match input.proof.as_deref() {
                Some(v) => v,
                None => {
                    println!("{}", json!({ "verified": false, "error": "missing proof" }));
                    std::process::exit(1);
                }
            };

            let commitment = match parse_commitment_32(commitment_str) {
                Ok(v) => v,
                Err(err) => {
                    println!("{}", json!({ "verified": false, "error": err }));
                    std::process::exit(1);
                }
            };
            let proof = match parse_proof(proof_str) {
                Ok(v) => v,
                Err(err) => {
                    println!("{}", json!({ "verified": false, "error": err }));
                    std::process::exit(1);
                }
            };
            let binding_tag = match parse_binding_tag(input.binding_tag_hex) {
                Ok(v) => v,
                Err(err) => {
                    println!("{}", json!({ "verified": false, "error": err }));
                    std::process::exit(1);
                }
            };

            let verified = if op == "verify-value-commitment" {
                zk::pedersen::verify_value_commitment_with_binding(
                    NgCompressed(commitment),
                    proof,
                    binding_tag.as_ref().map(|b| b.as_slice()),
                )
            } else {
                zk::txid_pedersen_proof::verify_txid_commitment_with_binding(
                    NgCompressed(commitment),
                    proof,
                    binding_tag.as_ref().map(|b| b.as_slice()),
                )
            };

            println!("{}", json!({ "verified": verified }));
        }
        _ => {
            println!("{}", json!({ "verified": false, "error": format!("unknown op: {op}") }));
            std::process::exit(1);
        }
    }
}

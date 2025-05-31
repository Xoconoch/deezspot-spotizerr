#!/usr/bin/env python3
"""
Specialized debugging script for investigating FLAC decryption issues.
This script downloads a track and analyzes the decryption process in detail.
"""

import os
import sys
import logging
import json
import argparse
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("flac_debug.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger('flac-debug')

# Import our modules
from deezspot.deezloader import DeeLogin
from deezspot.exceptions import BadCredentials, TrackNotFound
from deezspot.deezloader.__download_utils__ import analyze_flac_file

def debug_flac_decryption(arl_token, track_url, output_dir="debug_output"):
    """
    Debug the FLAC decryption process by downloading a track and analyzing each step.
    
    Args:
        arl_token: Deezer ARL token
        track_url: URL of the track to download
        output_dir: Directory to save output files
        
    Returns:
        Dict with debugging results
    """
    os.makedirs(output_dir, exist_ok=True)
    
    results = {
        "track_url": track_url,
        "steps": [],
        "success": False,
        "output_file": None,
        "analysis": None
    }
    
    try:
        # Step 1: Initialize DeeLogin
        logger.info("Step 1: Initializing DeeLogin")
        results["steps"].append({"step": "init", "status": "starting"})
        
        deezer = DeeLogin(arl=arl_token)
        results["steps"][-1]["status"] = "success"
        
        # Step 2: Download the track
        logger.info(f"Step 2: Downloading track from {track_url}")
        results["steps"].append({"step": "download", "status": "starting"})
        
        download_result = deezer.download_trackdee(
            track_url,
            output_dir=output_dir,
            quality_download="FLAC",
            recursive_quality=True,
            recursive_download=True
        )
        
        if not download_result.success:
            results["steps"][-1]["status"] = "failed"
            results["steps"][-1]["error"] = "Download failed"
            return results
        
        results["steps"][-1]["status"] = "success"
        results["output_file"] = download_result.song_path
        logger.info(f"Downloaded file to: {download_result.song_path}")
        
        # Step 3: Analyze the downloaded file
        logger.info("Step 3: Analyzing downloaded FLAC file")
        results["steps"].append({"step": "analyze", "status": "starting"})
        
        analysis = analyze_flac_file(download_result.song_path)
        results["analysis"] = analysis
        
        if analysis.get("has_flac_signature", False) and not analysis.get("potential_issues"):
            results["steps"][-1]["status"] = "success"
            results["success"] = True
            logger.info("FLAC analysis completed successfully - file appears valid")
        else:
            results["steps"][-1]["status"] = "warning"
            issues = analysis.get("potential_issues", [])
            results["steps"][-1]["issues"] = issues
            logger.warning(f"FLAC analysis found potential issues: {issues}")
        
        # Save detailed analysis to a JSON file
        analysis_file = os.path.join(output_dir, "flac_analysis.json")
        with open(analysis_file, 'w') as f:
            json.dump(analysis, f, indent=2)
        logger.info(f"Saved detailed analysis to {analysis_file}")
        
        return results
        
    except BadCredentials:
        logger.error("Invalid ARL token")
        results["steps"].append({"step": "error", "status": "failed", "error": "Invalid ARL token"})
        return results
    except TrackNotFound:
        logger.error(f"Track not found at URL: {track_url}")
        results["steps"].append({"step": "error", "status": "failed", "error": "Track not found"})
        return results
    except Exception as e:
        logger.error(f"Error during debugging: {str(e)}", exc_info=True)
        results["steps"].append({"step": "error", "status": "failed", "error": str(e)})
        return results

def main():
    parser = argparse.ArgumentParser(description="Debug FLAC decryption issues")
    parser.add_argument("--arl", help="Deezer ARL token")
    parser.add_argument("--track", help="Deezer track URL", default="https://www.deezer.com/us/track/2306672155")
    parser.add_argument("--output-dir", help="Output directory", default="debug_output")
    
    args = parser.parse_args()
    
    # Check for ARL token
    arl_token = args.arl or os.environ.get("DEEZER_ARL")
    if not arl_token:
        print("Error: Deezer ARL token not provided")
        print("Please provide with --arl or set the DEEZER_ARL environment variable")
        return 1
    
    # Run the debugging
    print(f"Starting FLAC decryption debugging for track: {args.track}")
    results = debug_flac_decryption(arl_token, args.track, args.output_dir)
    
    # Print summary
    print("\n===== Debugging Summary =====")
    for step in results["steps"]:
        status_icon = "✅" if step["status"] == "success" else "⚠️" if step["status"] == "warning" else "❌"
        print(f"{status_icon} {step['step'].capitalize()}: {step['status'].upper()}")
        
        if step["status"] == "failed" and "error" in step:
            print(f"   Error: {step['error']}")
        elif step["status"] == "warning" and "issues" in step:
            for issue in step["issues"]:
                print(f"   Issue: {issue}")
    
    if results["success"]:
        print("\n✅ FLAC file appears to be valid!")
        if results["output_file"]:
            print(f"Output file: {results['output_file']}")
        return 0
    else:
        print("\n❌ FLAC decryption had issues")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 
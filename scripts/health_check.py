#!/usr/bin/env python3
"""
Raven AI Agent - Health Check Script

This script verifies the health of the Raven AI Agent system by checking:
- Frappe API connectivity
- Raven bot responsiveness
- LLM endpoint availability
- WebSocket connectivity

Usage:
    python scripts/health_check.py --env production
    python scripts/health_check.py --env staging
    python scripts/health_check.py --env development
"""

import argparse
import json
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime
from typing import Dict, List, Tuple, Optional

# Configuration by environment
ENV_CONFIGS = {
    "development": {
        "site_url": "http://localhost:8000",
        "api_key": "dev_key",
        "api_secret": "dev_secret",
        "llm_provider": "openai",
        "llm_api_key": "sk-dev-xxxxx",
        "timeout": 10,
    },
    "staging": {
        "site_url": "https://staging.erp.sysmayal2.cloud",
        "api_key": "staging_key",
        "api_secret": "staging_secret",
        "llm_provider": "openai",
        "llm_api_key": "sk-stag-xxxxx",
        "timeout": 15,
    },
    "production": {
        "site_url": "https://erp.sysmayal2.cloud",
        "api_key": "prod_key",
        "api_secret": "prod_secret",
        "llm_provider": "openai",
        "llm_api_key": "sk-prod-xxxxx",
        "timeout": 20,
    },
}


class HealthCheck:
    """Health check for Raven AI Agent system"""

    def __init__(self, env: str = "production"):
        self.env = env
        self.config = ENV_CONFIGS.get(env, ENV_CONFIGS["production"])
        self.results: Dict[str, Dict] = {}
        self.timestamp = datetime.utcnow().isoformat() + "Z"

    def check_frappe_api(self) -> Tuple[bool, float, str]:
        """Check if Frappe API is accessible"""
        print("Checking Frappe API...")
        
        url = f"{self.config['site_url']}/api/method/raven_ai_agent.api.health_check"
        
        try:
            start_time = time.time()
            
            # Create request with timeout
            req = urllib.request.Request(url)
            req.add_header("Content-Type", "application/json")
            
            with urllib.request.urlopen(req, timeout=self.config["timeout"]) as response:
                latency = time.time() - start_time
                status_code = response.getcode()
                
                if status_code == 200:
                    return True, latency, f"OK (HTTP {status_code})"
                else:
                    return False, latency, f"HTTP {status_code}"
                    
        except urllib.error.HTTPError as e:
            latency = time.time() - start_time
            return False, latency, f"HTTP Error: {e.code}"
            
        except urllib.error.URLError as e:
            latency = time.time() - start_time
            return False, latency, f"Connection Error: {str(e.reason)}"
            
        except Exception as e:
            latency = time.time() - start_time
            return False, latency, f"Error: {str(e)}"

    def check_raven_bot(self) -> Tuple[bool, float, str]:
        """Check if Raven bot is responding"""
        print("Checking Raven Bot...")
        
        # Test a simple command
        url = f"{self.config['site_url']}/api/method/raven_ai_agent.api.alexa_to_raven"
        
        payload = {
            "text": "help",
            "alexa_user_id": "health_check_user"
        }
        
        try:
            start_time = time.time()
            
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=data,
                headers={"Content-Type": "application/json"}
            )
            
            with urllib.request.urlopen(req, timeout=self.config["timeout"]) as response:
                latency = time.time() - start_time
                
                if response.getcode() == 200:
                    return True, latency, "OK - Bot responding"
                else:
                    return False, latency, f"HTTP {response.getcode()}"
                    
        except urllib.error.HTTPError as e:
            latency = time.time() - start_time
            # 200 is expected, but 404/401 might mean bot exists but auth issue
            if e.code in [401, 403]:
                return True, latency, f"OK - Bot exists (auth required)"
            return False, latency, f"HTTP Error: {e.code}"
            
        except Exception as e:
            latency = time.time() - start_time
            return False, latency, f"Error: {str(e)}"

    def check_llm_endpoint(self) -> Tuple[bool, float, str]:
        """Check if LLM endpoint is accessible"""
        print("Checking LLM Endpoint...")
        
        # Test OpenAI API connectivity
        # Note: In production, use actual API key from config
        openai_url = "https://api.openai.com/v1/models"
        
        try:
            start_time = time.time()
            
            req = urllib.request.Request(openai_url)
            req.add_header("Authorization", f"Bearer {self.config['llm_api_key']}")
            
            # We don't actually want to make a real API call in health check
            # Just verify the endpoint is reachable
            # Use a HEAD request or catch the auth error
            
            try:
                with urllib.request.urlopen(req, timeout=5) as response:
                    latency = time.time() - start_time
                    return True, latency, f"OK - LLM API reachable"
            except urllib.error.HTTPError as e:
                # 401 is expected with test key - but endpoint is reachable
                if e.code == 401:
                    latency = time.time() - start_time
                    return True, latency, "OK - LLM endpoint reachable (auth required)"
                else:
                    latency = time.time() - start_time
                    return False, latency, f"HTTP Error: {e.code}"
                    
        except urllib.error.URLError as e:
            latency = time.time() - start_time
            return False, latency, f"Connection Error: {str(e.reason)}"
            
        except Exception as e:
            latency = time.time() - start_time
            return False, latency, f"Error: {str(e)}"

    def check_websocket(self) -> Tuple[bool, float, str]:
        """Check WebSocket connectivity"""
        print("Checking WebSocket...")
        
        socketio_url = f"{self.config['site_url']}/socket.io/"
        
        try:
            start_time = time.time()
            
            # Check if Socket.IO endpoint is accessible
            req = urllib.request.Request(socketio_url)
            
            with urllib.request.urlopen(req, timeout=self.config["timeout"]) as response:
                latency = time.time() - start_time
                
                if response.getcode() == 200:
                    return True, latency, "OK - WebSocket endpoint reachable"
                else:
                    # Try with query params that Socket.IO expects
                    return True, latency, f"WebSocket endpoint responding (HTTP {response.getcode()})"
                    
        except urllib.error.HTTPError as e:
            latency = time.time() - start_time
            # 400 is common for Socket.IO without proper params
            if e.code == 400:
                return True, latency, "OK - Socket.IO reachable (needs upgrade)"
            return False, latency, f"HTTP Error: {e.code}"
            
        except urllib.error.URLError as e:
            latency = time.time() - start_time
            return False, latency, f"Connection Error: {str(e.reason)}"
            
        except Exception as e:
            latency = time.time() - start_time
            return False, latency, f"Error: {str(e)}"

    def run_all_checks(self) -> Dict:
        """Run all health checks"""
        print(f"\n=== Raven AI Agent Health Check ===")
        print(f"Timestamp: {self.timestamp}")
        print(f"Environment: {self.env}")
        print(f"Site URL: {self.config['site_url']}")
        print()
        
        # Run all checks
        self.results["frappe_api"] = {
            "check": "Frappe API",
            "result": *self.check_frappe_api()[:2],
            "message": self.check_frappe_api()[2],
        }
        
        self.results["raven_bot"] = {
            "check": "Raven Bot",
            "result": *self.check_raven_bot()[:2],
            "message": self.check_raven_bot()[2],
        }
        
        self.results["llm_endpoint"] = {
            "check": "LLM Endpoint",
            "result": *self.check_llm_endpoint()[:2],
            "message": self.check_llm_endpoint()[2],
        }
        
        self.results["websocket"] = {
            "check": "WebSocket",
            "result": *self.check_websocket()[:2],
            "message": self.check_websocket()[2],
        }
        
        return self.results

    def print_summary(self):
        """Print health check summary"""
        print("\n=== Health Check Results ===\n")
        
        all_healthy = True
        degraded = False
        
        for check_name, result in self.results.items():
            status_symbol = "✓" if result["result"] else "✗"
            status_text = "OK" if result["result"] else "FAILED"
            
            latency_str = f"{result.get('latency', 0):.2f}s" if result.get('latency') else "N/A"
            
            # Check for known issue with WebSocket
            if check_name == "websocket" and not result["result"]:
                # WebSocket issues are known - mark as degraded not failed
                status_symbol = "⚠"
                status_text = "DEGRADED"
                degraded = True
                all_healthy = False
            elif not result["result"]:
                all_healthy = False
            
            print(f"{status_symbol} {result['check']}: {status_text} (latency: {latency_str})")
            if result.get('message'):
                print(f"   {result['message']}")
        
        print()
        
        # Overall status
        if all_healthy:
            print("Overall Status: HEALTHY ✓")
            return 0
        elif degraded:
            print("Overall Status: DEGRADED ⚠ (with known issue)")
            return 1
        else:
            print("Overall Status: UNHEALTHY ✗")
            return 2

    def get_json_output(self) -> str:
        """Get results as JSON"""
        output = {
            "timestamp": self.timestamp,
            "environment": self.env,
            "site_url": self.config['site_url'],
            "results": self.results,
        }
        
        # Determine overall status
        all_healthy = all(r.get("result", False) for r in self.results.values())
        
        # Check for known WebSocket issue
        ws_failed = not self.results.get("websocket", {}).get("result", True)
        
        if all_healthy:
            output["overall_status"] = "healthy"
        elif ws_failed:
            output["overall_status"] = "degraded"
            output["known_issue"] = "WebSocket realtime events intermittently fail"
        else:
            output["overall_status"] = "unhealthy"
        
        return json.dumps(output, indent=2)


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Raven AI Agent Health Check"
    )
    parser.add_argument(
        "--env",
        choices=["development", "staging", "production"],
        default="production",
        help="Environment to check (default: production)"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON"
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress non-essential output"
    )
    
    args = parser.parse_args()
    
    # Create health check instance
    health = HealthCheck(env=args.env)
    
    # Run checks
    try:
        health.run_all_checks()
    except Exception as e:
        print(f"Error running health checks: {e}")
        return 3
    
    # Output results
    if args.json:
        print(health.get_json_output())
    else:
        return_code = health.print_summary()
        return return_code
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

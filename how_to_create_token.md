# How to Create an Enphase Local API Access Token

The Enphase Envoy (IQ Gateway) with firmware D8.x requires a JWT token to access the local API.

## Steps

1. **Log in to Enlighten**
   - Go to https://enlighten.enphaseenergy.com
   - Sign in with your Enphase account

2. **Find your System ID**
   - In the Enphase app or Enlighten web portal, go to **Site Details**
   - Note the system identifier (numeric ID)

3. **Navigate to the token page**
   - Go to https://entrez.enphaseenergy.com/tokens
   - You must be logged in to Enlighten first

4. **Create the token**
   - **Select System**: Start typing your system identifier (found in Site Details). An autocomplete list will appear — select your system from the list.
   - **Select Gateway**: Choose your gateway from the dropdown (e.g. serial number `123456789012`)
   - Click **"Create access token"**

5. **Copy the token**
   - The JWT token will be displayed on the page
   - Copy it — it is valid for approximately 12 months

## Usage

Use the token to authenticate local API requests to the Envoy:

```bash
curl -s -k -H "Authorization: Bearer <TOKEN>" https://envoy.local/production.json
```

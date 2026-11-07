do not code this feature yet. But just wanted to understand. What we will need if we want to enable user to make the payments for using this as a service?

Yes. **Razorpay charges you as the merchant** for processing payments. Its India pricing currently lists a standard gateway fee of **2% plus applicable GST per successful payment**. Cards and net banking are supported, and standard UPI payments still incur Razorpay’s platform fee even though bank-to-bank UPI has zero MDR. There are no standard setup or annual maintenance fees listed. [Razorpay pricing](https://razorpay.com/pricing/)

Razorpay’s pricing page also advertises a **free period for eligible new merchants**, so your actual rate may depend on eligibility and offer terms. If you later choose recurring subscriptions, Razorpay lists a separate subscription fee in addition to the underlying payment gateway fee. [Razorpay Subscriptions](https://razorpay.com/subscriptions/)

So for the initial plan—**cards, UPI, and net banking**—budget for a fee on successful payments, then confirm the exact rate and any offer directly with Razorpay before signing up. No code changes have been made.


There are providers advertising **temporary free-payment offers**, but I didn’t find a clear permanent zero-fee option for cards, UPI, and net banking together.

- **PhonePe Payment Gateway** currently advertises zero gateway fees during a promotional period, and says it supports all three methods. The offer’s specific terms weren’t clear on the pricing page, so ask PhonePe to confirm the duration and eligibility in writing. [PhonePe pricing](https://business.phonepe.com/payment-gateway/pricing)
- **Cashfree** advertises zero gateway fees for eligible new merchants up to **₹20 lakh in cumulative transactions**. The offer has exclusions and conditions; GST may still apply, and standard fees apply after it ends. [Cashfree pricing and offer terms](https://www.cashfree.com/payment-gateway-charges/)
- **PayU** lists no setup or annual fee, but that doesn’t mean free processing: its listed standard rate is 2% for domestic cards and net banking, with UPI pricing varying by business type and volume. [PayU pricing](https://payu.in/pricing/)

So Cashfree and PhonePe are worth checking for a launch offer. Ask each for the **effective cost for cards, UPI, and net banking**, including taxes and what happens after the offer.


Yes—**if the 2% gateway fee applies**:

- Gateway fee: ₹500 × 2% = **₹10**
- GST on that fee (assuming 18%): ₹10 × 18% = **₹1.80**
- Total deduction: **₹11.80**, leaving **₹488.20** from the ₹500 payment.

Because you’re describing a **monthly recurring subscription**, Razorpay may also charge a separate subscription fee. Its current Subscriptions page lists an additional fee on top of the payment gateway fee, so the actual deduction could be higher than ₹11.80. Confirm the recurring-payment rate and any introductory offer with Razorpay before setting your plan price. [Razorpay pricing](https://razorpay.com/pricing/), [Razorpay Subscriptions](https://razorpay.com/subscriptions/)


**Possibly, if you’re registered for GST or required to register.** Then GST on your service is separate from the GST Razorpay charges you on its gateway fee. You would show your tax on the customer’s invoice, collect it, report it, and pay the amount due to the government, accounting for any eligible input tax credit.

For service providers, the general registration threshold is **₹20 lakh in aggregate annual turnover**, or ₹10 lakh in certain states. There are exceptions, so your location, total business turnover across your PAN, and customer locations can matter. [CBIC registration FAQ](https://cbic-gst.gov.in/sectoral-faq.html)

Don’t assume the GST rate on your subscription is the same as the rate on Razorpay’s fee. Ask a chartered accountant to confirm whether you need to register, how your service is classified, and what rate and invoice treatment apply. Then you can decide whether your ₹500 plan is **₹500 plus applicable GST** or **₹500 inclusive of GST**.


The payment provider collects the customer’s payment, then **pays out the net amount to the bank account you registered with it** after merchant onboarding/KYC. It deducts its fees before the payout, and you can reconcile the payout in the provider’s dashboard. Razorpay describes this as settling the remaining amount to your registered bank account according to your account’s settlement schedule. [Razorpay pricing](https://razorpay.com/pricing/)

For the ₹500 example, **assuming only a 2% gateway fee plus 18% GST on that fee**, the payout would be ₹488.20. A recurring subscription may have an additional subscription fee, which would reduce it further; check the actual rate and payout schedule in the merchant account.

If you’re registered for GST, any GST you charge the customer on your ₹500 service is separate: it’s your tax liability to report and pay, not the gateway fee that Razorpay deducts.

**Shopify** and **WooCommerce** are tools for building online stores:

- **Shopify** is a hosted e-commerce service. It provides the store website, product catalog, checkout, and order management.
- **WooCommerce** is an e-commerce plugin for websites built with WordPress. It adds store and checkout features to a WordPress site.

Payment providers mention them because merchants often connect payments to these store platforms. **Your app is a custom React and Django application**, so you wouldn’t need Shopify or WooCommerce; payments would be integrated directly into your existing portal.





Worked for 24s



Yes. You can add payments later without changing the patent-analysis flow much. React would provide the billing screens, Django would manage billing and access, and the payment provider would process the transaction. FastAPI could remain an internal analysis service.

The main pieces would be:
1. Decide what customers pay for. For example: a monthly subscription, a set number of analyses, or a subscription with usage limits. Decide whether the payer is an individual or an organization, who can manage billing, and what happens when a payment fails or a plan is cancelled.
2. Choose a payment provider. That depends on where your business is based, where your customers are, and which payment methods and billing model you need. Providers such as Razorpay offer subscription options, but eligibility, fees, and available payment methods should be checked for your business. Razorpay Subscriptions
3. Add billing records to Django’s database. For this app, a subscription could belong to an organization. Individual users already have personal workspaces, so those could have subscriptions too. Django would track the provider’s customer and subscription IDs, the plan, status, renewal dates, and analysis usage. You would also need to decide which organization users can buy or change plans.
4. Add a checkout flow. Django creates the checkout with the provider, and React sends the user to the provider’s payment page. Using a hosted payment page means the app doesn’t handle or store card numbers.
5. Update access from verified payment events. After checkout, the browser’s return to your app is useful for showing a message, but shouldn’t be the proof of payment. The provider sends Django a signed webhook; Django verifies it and updates the subscription. Webhook handling needs to tolerate retries and duplicate events. Razorpay webhook guidance
6. Enforce the plan in Django. Before starting an analysis, Django checks the subscription and remaining allowance. The React interface can show limits and upgrade prompts, but the server must enforce them.
You’d also need to plan for renewals, failed payments, cancellations, refunds, invoices, taxes, and customer support. Tax and payment requirements depend on where you operate and sell, so those details should be reviewed before going live.

  
5:41 PM







ok. I would like to stick to credit card/debit card and upi payments to begin with.







5:49 PM






That sets the initial payment methods: credit/debit cards and UPI. The app can offer them through a provider’s hosted checkout, keeping card details out of your system.

The next decision is how to charge: one-time payment per analysis or credit pack, versus a recurring subscription. Recurring billing requires support for card or UPI mandates, not just a one-time checkout. Razorpay, for example, lists cards and UPI among its subscription payment options; we’d confirm current availability and terms before choosing a provider. Razorpay Subscriptions

No payment code has been added.

  
5:49 PM
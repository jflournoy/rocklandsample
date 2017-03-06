# download_rockland_raw_bids.py
#
# Authors: Daniel Clark, John Pellman 2015/2016

'''
This script downloads data from the NKI Rockland Sample Lite releases
stored in the cloud in BIDS format.  You can specify sex, age range, handedness,
session, scan type (anatomical, functional, dwi) and to limit your download to a subset of the sample.
If no options are specified, all available files are downloaded.

Use the '-h' to get more information about command line usage.
'''
# Import packages
import os

# Constants
SESSIONS = ['NFB3', 'DS2', 'NFB2', 'NFBR2', 'CLG2', 'CLGR', 'CLG4', 'CLG2R', 'CLG3', 'NFBR2A', 'CLG4R', 'NFB2R', 'DSA', 'CLGA', 'NFBA', 'CLG2A', 'CLG5', 'CLG', 'NFBAR']
SCANS = ['anat', 'func', 'dwi', 'fmap']
# Mapping colloquial names for the series to BIDS names.
SERIES_MAP = {
'CHECKERBOARD1400':'task-CHECKERBOARD_acq-1400',
'CHECKERBOARD645':'task-CHECKERBOARD_acq-645',
'RESTCAP':'task-rest_acq-CAP',
'REST1400':'task-rest_acq-1400',
'BREATHHOLD1400':'task-BREATHHOLD_acq-1400',
'REST645':'task-rest_acq-645',
'RESTPCASL':'task-rest_pcasl',
'DMNTRACKINGTEST':'task-DMNTRACKINGTEST',
'DMNTRACKINGTRAIN':'task-DMNTRACKINGTRAIN',
'MASK':'mask',
'MSIT':'task-MSIT',
'PEER1':'task-PEER1',
'PEER2':'task-PEER2',
'MORALDILEMMA':'task-MORALDILEMMA'
}

# Main collect and download function
def collect_and_download(out_dir,
                         less_than=0, greater_than=0, sex='', handedness='',
                         sessions=SESSIONS,
                         scans=SCANS,
                         series=SERIES_MAP.keys(),
                         derivatives=False,
                         dryrun=False):
    '''
    Function to collect and download images from the Rockland sample 
    directory on FCP-INDI's S3 bucket

    Parameters
    ----------
    out_dir : string
        filepath to a local directory to save files to
    less_than : float
        upper age (years) threshold for participants of interest
    greater_than : float
        lower age (years) threshold for participants of interest
    sex : string
        'M' or 'F' to indicate whether to download male or female data
    handedness : string
        'R' or 'L' to indicate whether to download right-handed or
        left-handed participants
    sessions : list
        the session names (e.g.,'CLG5','NFB3')
    scan : list
        the scan types to download.  Can be 'anat','func','dwi' or 'fmap'.
    series : list
        the series to download (for functional scans)
    derivatives : boolean
        whether or not to download data derivatives for functional scans
    dryrun : boolean
        whether or not to perform a dry run (i.e., no actual downloads,
        just listing files that would be downloaded)
    Returns
    -------
    boolean
        Returns true if the download was successful, false otherwise.
    '''
    # Import packages
    import pandas
    import boto3
    import botocore
    # For anonymous access to the bucket.
    from botocore import UNSIGNED
    from botocore.client import Config
    from botocore.handlers import disable_signing

    # Init variables
    s3_bucket_name = 'fcp-indi'
    s3_prefix = 'data/Projects/RocklandSample/RawDataBIDS'

    # Fetch bucket
    s3 = boto3.resource('s3')
    s3.meta.client.meta.events.register('choose-signer.s3.*', disable_signing)	
    s3_bucket = s3.Bucket(s3_bucket_name)

    # Remove series that aren't in the series map keys.
    series = [ s for s in series if s in SERIES_MAP.keys() ]

    # If output path doesn't exist, create it
    if not os.path.exists(out_dir) and not dryrun:
        print 'Could not find %s, creating now...' % out_dir
        os.makedirs(out_dir)

    # Load the participants.tsv file from S3
    s3_client = boto3.client('s3', config=Config(signature_version=UNSIGNED))
    participants_obj = s3_client.get_object(Bucket=s3_bucket_name, Key = '/'.join([s3_prefix,'participants.tsv']))
    participants_df = pandas.read_csv(participants_obj['Body'], delimiter='\t', na_values=['n/a'])

    # Init a list to store paths.
    print 'Collecting images of interest...'
    s3_keys = s3_bucket.objects.filter(Prefix=s3_prefix)
    s3_keylist = [key.key for key in s3_keys]

    # Remove the participants for whom age range, handedness and sex do not conform to the criteria.
    if less_than:
        participants_df = participants_df[participants_df['age'] < less_than]
    if greater_than:
        participants_df = participants_df[participants_df['age'] > greater_than]
    if sex == 'M':
        participants_df = participants_df[participants_df['sex'] == 'MALE']
    elif sex == 'F':
        participants_df = participants_df[participants_df['sex'] == 'FEMALE']
    if handedness == 'R':
        participants_df = participants_df[participants_df['handedness'] == 'RIGHT']
    elif handedness == 'L':
        participants_df = participants_df[participants_df['handedness'] == 'LEFT']

    if len(participants_df) == 0:
        print 'No participants meet the criteria given.  No download will be initiated.'
        return

    # Generate a list of participants to filter on.
    participants_filt = ['sub-'+ label + '/' for label in participants_df['participant_id'].tolist()]

    # Generate a list of sessions to filter on.
    sessions_filt = ['ses-' + session + '/' for session in sessions]

    # Generate a list of series to filter on.
    series_filt = [SERIES_MAP[s] for s in series]

    # Fetch top-level JSONs first.
    json_keylist = [key for key in s3_keylist for s in series_filt if s in key and 'json' in key and 'sub' not in key]
   
    # Applying filters.
    s3_keylist = [key for key in s3_keylist for p in participants_filt if p in key]
    s3_keylist = [key for key in s3_keylist for s in sessions_filt if s in key]
    s3_keylist = [key for key in s3_keylist for s in scans if s in key]
    s3_keylist = [key for key in s3_keylist for s in series_filt if (s in key) or ('func' not in key) ]

    # Add back top-level files
    s3_keylist.extend(json_keylist)
    s3_keylist.append('/'.join([s3_prefix, 'CHANGES']))
    s3_keylist.append('/'.join([s3_prefix, 'README']))
    s3_keylist.append('/'.join([s3_prefix, 'dataset_description.json']))

    # And download the items
    total_num_files = len(s3_keylist)
    files_downloaded = len(s3_keylist)
    for path_idx, s3_path in enumerate(s3_keylist):
        rel_path = s3_path.replace(s3_prefix, '')
        rel_path = rel_path.lstrip('/')
        download_file = os.path.join(out_dir, rel_path)
        download_dir = os.path.dirname(download_file)
        if not os.path.exists(download_dir) and not dryrun:
            os.makedirs(download_dir)
        try:
            if not os.path.exists(download_file):
                if dryrun:
                    print 'Would download to: %s' % download_file
                else:
                    print 'Downloading to: %s' % download_file
                    with open(download_file, 'wb') as f:
                        s3_client.download_fileobj(s3_bucket_name, s3_path, f)
                    print '%.3f%% percent complete' % \
                          (100*(float(path_idx+1)/total_num_files))
            else:
                print 'File %s already exists, skipping...' % download_file
                files_downloaded -= 1
        except Exception as exc:
            print 'There was a problem downloading %s.\n'\
                  'Check input arguments and try again.' % s3_path
            print exc
    # Print all done
    if dryrun:
        print '%d files would be downloaded for %d participant(s).' % (files_downloaded,len(participants_df))
    else:
        print '%d files downloaded for %d participant(s).' % (files_downloaded,len(participants_df))

    if not dryrun:
        print 'Saving out revised participants.tsv and session tsv files.'
        # Save out revised participants.tsv to output directory, if a participants.tsv already exists, open it and append it to the new one.
        if os.path.isfile(os.path.join(out_dir, 'participants.tsv')):
            old_participants_df = pandas.read_csv(os.path.join(out_dir, 'participants.tsv'), delimiter='\t', na_values=['n/a', 'N/A'])
            participants_df = participants_df.append(old_participants_df, ignore_index=True)
            participants_df.drop_duplicates(inplace=True)
            os.remove(os.path.join(out_dir, 'participants.tsv'))
        participants_df.to_csv(os.path.join(out_dir, 'participants.tsv'), sep="\t", na_rep="n/a", index=False)

        # Separate list for sessions TSVs.
        session_keylist = [key.key for key in s3_keys if 'sessions.tsv' in key.key]
        session_keylist = [key for key in session_keylist for p in participants_filt if p in key]
        # Save out revised session tsvs to output directory; if already exists, open it and merge with the new one.
        for session_key in session_keylist:
            participant = session_key.split('/')[-2]
            sessions_obj = s3_client.get_object(Bucket=s3_bucket_name, Key=session_key )
            sessions_df = pandas.read_csv(sessions_obj['Body'], delimiter='\t', na_values=['n/a'])
            # Drop all sessions not in specified.
            sessions_df = sessions_df[sessions_df['session_id'].isin(sessions_filt)]
            # Save out revised sessions tsv to output directory, if a sessions tsv already exists, open it and append it to the new one.
            if os.path.isfile(os.path.join(out_dir, participant, participant+'_sessions.tsv')):
                old_sessions_df = pandas.read_csv(os.path.join(out_dir, participant, participant+'_sessions.tsv'), delimiter='\t', na_values=['n/a', 'N/A'])
                sessions_df = sessions_df.append(old_sessions_df, ignore_index=True)
                sessions_df.drop_duplicates(inplace=True)
                os.remove(os.path.join(out_dir, participant, participant+'_sessions.tsv'))
            sessions_df.to_csv(os.path.join(out_dir, participant, participant+'_sessions.tsv'), sep="\t", na_rep="n/a", index=False)
    print 'Done!'

# Make module executable
if __name__ == '__main__':
    # Import packages
    import argparse
    import sys

    # Init arparser
    parser = argparse.ArgumentParser(description=__doc__)

    # Required arguments
    parser.add_argument('-o', '--out_dir', required=True, type=str,
                        help='Path to local folder to download files to')

    # Optional arguments
    parser.add_argument('-lt', '--less_than', required=False,
                        type=float, help='Upper age threshold (in years) of '\
                                         'particpants to download (e.g. for '\
                                         'subjects 30 or younger, \'-lt 31\')')
    parser.add_argument('-gt', '--greater_than', required=False,
                        type=float, help='Lower age threshold (in years) of '\
                                       'particpants to download (e.g. for '\
                                       'subjects 31 or older, \'-gt 30\')')
    parser.add_argument('-x', '--sex', required=False, type=str,
                        help='Participant sex of interest to download only '\
                             '(e.g. \'M\' or \'F\')')
    parser.add_argument('-m', '--handedness', required=False, type=str,
                        help='Participant handedness to download only '\
                             '(e.g. \'R\' or \'L\')')
    parser.add_argument('-v', '--sessions', required=False, nargs='*', type=str,
                        help='A space-separated list of session (visit) codes '\
                             'to download (e.g. \'NFB3\',\'CLG2\')')
    parser.add_argument('-t', '--scans', required=False, nargs='*', type=str,
                        help='A space-separated list of scan types '\
                             'to download (e.g. \'anat\',\'dwi\')')
    parser.add_argument('-e', '--series', required=False, nargs='*', type=str,
                        help='A space-separated list of series codes '\
                             'to download (e.g. \'DMNTRACKINGTRAIN\',\'DMNTRACKINGTEST\')')
    parser.add_argument('-d', '--derivatives', required=False, action='store_true',
                        help='Download derivatives (despiked physio, masks) in addition to raw data?')
    parser.add_argument('-n', '--dryrun', required=False, action='store_true',
                        help='Perform a dry run to see how many files would be downloaded.')

    # Parse and gather arguments
    args = parser.parse_args()

    # Init variables
    out_dir = os.path.abspath(args.out_dir)
    kwargs = {}
    if args.less_than:
        kwargs['less_than'] = args.less_than
        print 'Using upper age threshold of %d...' % kwargs['less_than']
    else:
        print 'No upper age threshold specified'
    if args.greater_than:
        kwargs['greater_than'] = args.greater_than
        print 'Using lower age threshold of %d...' % kwargs['greater_than']
    else:
        print 'No lower age threshold specified'
    if args.sex:
        kwargs['sex'] = args.sex.upper()
        if kwargs['sex'] == 'M':
            print 'Downloading only male participants...'
        elif kwargs['sex'] == 'F':
            print 'Downloading only female participants...'
        else:
            print 'Input for sex \'%s\' was not \'M\' or \'F\'.' % kwargs['sex']
            print 'Please check script syntax and try again.'
            sys.exit(1)
    else:
        print 'No sex specified, using all sexes...'
    if args.handedness:
        kwargs['handedness'] = args.handedness.upper()
        if kwargs['handedness'] == 'R':
            print 'Downloading only right-handed participants...'
        elif kwargs['handedness'] == 'L':
            print 'Downloading only left-handed participants...'
        else:
            print 'Input for handedness \'%s\' was not \'L\' or \'R\'.' % kwargs['handedness']
            print 'Please check script syntax and try again.'
            sys.exit(1)
    if args.sessions:
        kwargs['sessions'] = args.sessions
        for session in kwargs['sessions']:
            if session not in SESSIONS:
                print 'Session \'%s\' is not a valid session name.' % session
                print 'Please check script syntax and try again.'
                sys.exit(1)
        print 'Sessions to download: ' + ' '.join(kwargs['sessions'])
    if args.scans:
        kwargs['scans'] = args.scans
        for scan in kwargs['scans']:
            if scan not in SCANS:
                print 'Scan \'%s\' is not a valid scan name.' % scan
                print 'Please check script syntax and try again.'
                sys.exit(1)
        print 'Scans to download: ' + ' '.join(kwargs['scans'])
    if args.series:
        kwargs['series'] = args.series
        for series in kwargs['series']:
            if series not in SERIES_MAP.keys():
                print 'Series \'%s\' is not a valid series name.' % series
                print 'Please check script syntax and try again.'
                sys.exit(1)
        print 'Series to download: ' + ' '.join(kwargs['series'])
    if args.derivatives:
        kwargs['derivatives'] = args.derivatives
        print 'Data derivatives will be downloaded.'
    if args.dryrun:
        kwargs['dryrun'] = args.dryrun
        print 'Running download as a dry run.'

    # Call the collect and download routine
    collect_and_download(out_dir, **kwargs)

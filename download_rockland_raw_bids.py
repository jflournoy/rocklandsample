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
    Function to collect and download images from the ABIDE preprocessed
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
    import urllib
    import pandas

    # Init variables
    s3_prefix = 'https://s3.amazonaws.com/fcp-indi/data/Projects/'\
                'RocklandSample/RawDataBIDS'
    s3_participants = '/'.join([s3_prefix, 'participants.tsv'])

    # Remove series that aren't in the series map keys.
    for serie in series:
        if serie not in SERIES_MAP.keys():
            print 'Warning: %s not in series map.\
                    Check orthography and re-run.' % serie
            series.remove(serie)

    # If output path doesn't exist, create it
    if not os.path.exists(out_dir) and not dryrun:
        print 'Could not find %s, creating now...' % out_dir
        os.makedirs(out_dir)

    # Load the participants.tsv file from S3
    try:
        s3_participants_file = urllib.urlopen(s3_participants)
        participants_df = pandas.read_csv(s3_participants_file, delimiter='\t',
                na_values=['n/a', 'N/A'])
    except Exception as exc:
        print 'Could not fetch participants.tsv file to begin download.\
                Error below:'
        print exc

    # Init a list to store paths.
    print 'Collecting images of interest...'
    s3_paths = []

    # Add the top-level sidecar JSONs to the download list.
    for scan in scans:
        if scan == 'func':
            for serie in series:
                s3_paths.append('/'.join([s3_prefix,
                    '_'.join([SERIES_MAP[serie], 'bold.json'])]))
        elif scan == 'dwi':
            s3_paths.append('/'.join([s3_prefix, 'dwi.json']))
        elif scan == 'fmap':
            s3_paths.append('/'.join([s3_prefix, 'phasediff.json']))

    # Other top-level files
    s3_paths.append('/'.join([s3_prefix, 'CHANGES']))
    s3_paths.append('/'.join([s3_prefix, 'README']))
    s3_paths.append('/'.join([s3_prefix, 'dataset_description.json']))

    # Remove the participants for whom age range, handedness and sex do not conform to the criteria.
    if less_than:
        age_lt_df = participants_df.where(participants_df['age'] < less_than)
    if greater_than:
        age_gt_df = participants_df.where(participants_df['age'] > greater_than)
    if less_than and greater_than:
        participants_df = pandas.merge(age_lt_df, age_gt_df,
                on=participants_df.columns.tolist())
    elif less_than:
        participants_df = age_lt_df
    elif greater_than:
        participants_df = age_gt_df
    if sex == 'M':
        participants_df.where(participants_df['sex'] == 'MALE', inplace=True)
    elif sex == 'F':
        participants_df.where(participants_df['sex'] == 'FEMALE', inplace=True)
    if handedness == 'R':
        participants_df.where(participants_df['handedness'] == 'RIGHT',
                inplace=True)
    elif handedness == 'L':
        participants_df.where(participants_df['handedness'] == 'LEFT',
                inplace=True)
    participants_df.dropna(inplace=True)

    # Generate a dictionary of participants and their session TSVs.
    participant_dirs = ['sub-'+label for label in participants_df['participant_id'].tolist()]
    session_tsvs = [participant+'_sessions.tsv' for participant in participant_dirs]
    participants = dict(zip(participant_dirs, session_tsvs))

    # Add 'ses-' prefix to session names.
    sessions = ['ses-' + session for session in sessions]

    # Init a dictionary that will pair participants and their session TSVs as dataframes.
    participant_sessions={}

    # Create participant-level directories if they do not exist already.
    for participant in participants.keys():
        # Load every sessions tsv for each participant.
        session_tsv = participants[participant]
        s3_sessions = '/'.join([s3_prefix, participant, session_tsv])
        # Load the session tsv file from S3
        try:
            print 'Getting info from %s' % s3_sessions
            s3_sessions_file = urllib.urlopen(s3_sessions)
            sessions_df = pandas.read_csv(s3_sessions_file, delimiter='\t', na_values=['n/a', 'N/A'])
        except Exception as exc:
            print 'Could not fetch sessions tsv file %s.\
                    Error below:' % s3_sessions
            print exc
            print 'Skipping session'
            continue

        # Remove sessions that we do not want from sessions tsv.
        sessions_df.where(sessions_df['session_id'].isin(sessions), inplace=True)
        sessions_df.dropna(inplace=True)
        # If there are no sessions of the desired type in this TSV, continue to the next particiapnt.
        if len(sessions_df) == 0:
            participants_df.where(participants_df['participant_id'] != participant.replace('sub-',''), inplace=True)
            participants_df.dropna(inplace=True)
            continue

        participant_sessions[participant] = sessions_df

        for session in sessions:
            for scan in scans:
                if scan == 'anat':
                    s3_paths.append('/'.join([s3_prefix, participant, session, scan, '_'.join([participant, session, 'T1w'])+'.nii.gz']))
                elif scan == 'func':
                    for serie in series:
                        if derivatives:
                            s3_paths.append('/'.join([s3_prefix, 'derivatives', participant, session, scan, '_'.join([participant, session, SERIES_MAP[serie], 'recording-despiked', 'physio'])+'.tsv.gz']))
                            s3_paths.append('/'.join([s3_prefix, 'derivatives', participant, session, scan, '_'.join([participant, session, SERIES_MAP[serie], 'recording-despiked', 'physio'])+'.json']))
                            if serie == 'MASK':
                                s3_paths.append('/'.join([s3_prefix, 'derivatives', participant, session, scan, '_'.join([participant, session, SERIES_MAP[serie], 'bold'])+'.nii.gz']))
                                s3_paths.append('/'.join([s3_prefix, 'derivatives', participant, session, scan, '_'.join([participant, session, SERIES_MAP[serie], 'bold'])+'.json']))
                                continue
                        elif serie == 'MASK':
                            continue
                        s3_paths.append('/'.join([s3_prefix, participant, session, scan, '_'.join([participant, session, SERIES_MAP[serie], 'bold'])+'.nii.gz']))
                        s3_paths.append('/'.join([s3_prefix, participant, session, scan, '_'.join([participant, session, SERIES_MAP[serie], 'bold'])+'.json']))
                        s3_paths.append('/'.join([s3_prefix, participant, session, scan, '_'.join([participant, session, SERIES_MAP[serie], 'events'])+'.tsv']))
                        s3_paths.append('/'.join([s3_prefix, participant, session, scan, '_'.join([participant, session, SERIES_MAP[serie], 'physio'])+'.tsv.gz']))
                        s3_paths.append('/'.join([s3_prefix, participant, session, scan, '_'.join([participant, session, SERIES_MAP[serie], 'physio'])+'.json']))
                elif scan == 'dwi':
                    if derivatives:
                        s3_paths.append('/'.join([s3_prefix, 'derivatives', participant, session, scan, '_'.join([participant, session, 'dwi', 'recording-despiked', 'physio'])+'.tsv.gz']))
                        s3_paths.append('/'.join([s3_prefix, 'derivatives', participant, session, scan, '_'.join([participant, session, 'dwi', 'recording-despiked', 'physio'])+'.json']))
                    s3_paths.append('/'.join([s3_prefix, participant, session, scan, '_'.join([participant, session, 'dwi'])+'.nii.gz']))
                    s3_paths.append('/'.join([s3_prefix, participant, session, scan, '_'.join([participant, session, 'dwi'])+'.bval']))
                    s3_paths.append('/'.join([s3_prefix, participant, session, scan, '_'.join([participant, session, 'dwi'])+'.bvec']))
                    s3_paths.append('/'.join([s3_prefix, participant, session, scan, '_'.join([participant, session, 'dwi'])+'.json']))
                    s3_paths.append('/'.join([s3_prefix, participant, session, scan, '_'.join([participant, session, 'dwi', 'physio'])+'.tsv.gz']))
                    s3_paths.append('/'.join([s3_prefix, participant, session, scan, '_'.join([participant, session, 'dwi', 'physio'])+'.json']))
                elif scan == 'fmap':
                    s3_paths.append('/'.join([s3_prefix, participant, session, scan, '_'.join([participant, session, 'magnitude1'])+'.nii.gz']))
                    s3_paths.append('/'.join([s3_prefix, participant, session, scan, '_'.join([participant, session, 'phasediff'])+'.nii.gz']))
                    s3_paths.append('/'.join([s3_prefix, participant, session, scan, '_'.join([participant, session, 'phasediff'])+'.json']))

    if len(participants_df) == 0:
        print 'No participants meet the criteria given.  No download will be initiated.'
        return

    # Remove the files that don't exist by iterating through the list and trying to fetch them.
    urls = [url for url in s3_paths]
    for url in urls:
        try:
            url_head = urllib.urlopen(url).readline()
            if 'xml' in url_head:
                s3_paths.remove(url)
        except Exception as exc:
            print 'Problem determining if %s is a valid file to download:'
            print exc
            print 'Removing for now.  Re-run script to retry.'
            s3_paths.remove(url)

    # And download the items
    total_num_files = len(s3_paths)
    files_downloaded = len(s3_paths)
    for path_idx, s3_path in enumerate(s3_paths):
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
                    urllib.urlretrieve(s3_path, download_file)
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
    print 'Done!'

    if not dryrun:
        print 'Saving out revised participants.tsv and session tsv files.'
        # Save out revised participants.tsv to output directory, if a participants.tsv already exists, open it and append it to the new one.
        if os.path.isfile(os.path.join(out_dir, 'participants.tsv')):
            old_participants_df = pandas.read_csv(os.path.join(out_dir, 'participants.tsv'), delimiter='\t', na_values=['n/a', 'N/A'])
            participants_df=participants_df.append(old_participants_df, ignore_index=True)
            participants_df.drop_duplicates(inplace=True)
            os.remove(os.path.join(out_dir, 'participants.tsv'))
        participants_df.to_csv(os.path.join(out_dir, 'participants.tsv'), sep="\t", na_rep="n/a", index=False)

        # Save out revised session tsvs to output directory; if already exists, open it and merge with the new one.
        for participant in participant_sessions.keys():
            sessions_df = participant_sessions[participant]
           # Save out revised sessions tsv to output directory, if a sessions tsv already exists, open it and append it to the new one.
            if os.path.isfile(os.path.join(out_dir, participant, participant+'_sessions.tsv')):
                old_sessions_df = pandas.read_csv(os.path.join(out_dir, participant, participant+'_sessions.tsv'), delimiter='\t', na_values=['n/a', 'N/A'])
                sessions_df=sessions_df.append(old_sessions_df, ignore_index=True)
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
